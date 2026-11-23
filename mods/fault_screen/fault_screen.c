/* Fault screen: when the processor faults, show where on the display and stop, so the owner can photograph it.

   The firmware's four fault handlers (HardFault, MemManage, BusFault, UsageFault) are a lone `bx lr`, so a fault returns to the
   same instruction for ever and the unit just stands with nothing on the screen (hw.faults.vectors). Word hooks point the four
   vector words at fault_screen_fault instead. It reads the faulting PC and LR from the exception frame, moves to a stack of its
   own (the fault may be a broken stack), draws the fault straight into the display controller by polling its SPI port, and
   stands. Nothing of the firmware is used: no task, no lock, no DMA, no allocation, no firmware font.

   Adapted for 404Lab from the crash screen of the maintainer's private mod, which showed three real faults on the owner's unit
   (hk.fault-screen). The display: an SSD1309 on LPSPI4 at 0x403A0000, chip select 0, data/command on GPIO2 pin 1 (hw.display.port).

   On the main screen HOLD + ROLL makes a fault on purpose (an undefined instruction), to see the screen work. Power off and on
   to leave it. Everything else goes on to the firmware unchanged. */
#include <stdint.h>

enum { KEY_DOWN = 5, KEY_UP = 6, HOLD = 0x11, ROLL = 0x21, MAIN_PAGE = 1 };
struct event { short type, code, value; };

#define CURRENT_PAGE (*(volatile unsigned short *)0x80245880) /* stock 5.52 and DOOM OS 0.7.3 and 0.7.4 */

#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define SPI_CR   REG(0x403A0010u)
#define SPI_SR   REG(0x403A0014u)
#define SPI_DER  REG(0x403A001Cu)
#define SPI_FSR  REG(0x403A005Cu)
#define SPI_TCR  REG(0x403A0060u)
#define SPI_TDR  REG(0x403A0064u)
#define DC_SET   REG(0x401BC084u)  /* GPIO2 DR_SET */
#define DC_CLEAR REG(0x401BC088u)  /* GPIO2 DR_CLEAR */
#define DC_PIN   2u
#define CFSR     REG(0xE000ED28u)
#define HFSR     REG(0xE000ED2Cu)
#define MMFAR    REG(0xE000ED34u)
#define BFAR     REG(0xE000ED38u)

/* 5 x 7 glyphs for ' ' to 'Z', one byte per row, top row first, bit 4 the leftmost pixel. Drawn for this example. */
static const uint8_t FONT[] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* ' ' */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '!', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '"', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '#', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '$', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '%', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '&', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* "'", not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '(', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* ')', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '*', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '+', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08,  /* ',' */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '-', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C,  /* '.' */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '/', not drawn */
    0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E,  /* '0' */
    0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E,  /* '1' */
    0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F,  /* '2' */
    0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E,  /* '3' */
    0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02,  /* '4' */
    0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E,  /* '5' */
    0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E,  /* '6' */
    0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08,  /* '7' */
    0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E,  /* '8' */
    0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C,  /* '9' */
    0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00,  /* ':' */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* ';', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '<', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '=', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '>', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '?', not drawn */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  /* '@', not drawn */
    0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11,  /* 'A' */
    0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E,  /* 'B' */
    0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E,  /* 'C' */
    0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E,  /* 'D' */
    0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F,  /* 'E' */
    0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10,  /* 'F' */
    0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F,  /* 'G' */
    0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11,  /* 'H' */
    0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E,  /* 'I' */
    0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C,  /* 'J' */
    0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11,  /* 'K' */
    0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F,  /* 'L' */
    0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11,  /* 'M' */
    0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11,  /* 'N' */
    0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E,  /* 'O' */
    0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10,  /* 'P' */
    0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D,  /* 'Q' */
    0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11,  /* 'R' */
    0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E,  /* 'S' */
    0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04,  /* 'T' */
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E,  /* 'U' */
    0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04,  /* 'V' */
    0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A,  /* 'W' */
    0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11,  /* 'X' */
    0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04,  /* 'Y' */
    0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F,  /* 'Z' */
};

/* The frame as the controller takes it: 8 pages of 128 columns, one byte per column, bit 0 the top row of the page. */
static uint8_t screen[1024];
uint32_t fault_screen_stack[256] __attribute__((aligned(8)));
volatile uint32_t fault_screen_shown;

static void glyph(unsigned x, unsigned line, char c)
{
    if (c >= 'a' && c <= 'z')
        c = (char)(c - 32);
    if (c < ' ' || c > 'Z')
        c = ' ';
    const uint8_t *rows = &FONT[(c - ' ') * 7];
    for (unsigned col = 0; col < 5 && x + col < 128; ++col)
        for (unsigned row = 0; row < 7; ++row)
            if (rows[row] & (0x10u >> col))
                screen[line * 128 + x + col] |= (uint8_t)(1u << row);
}

static unsigned text(unsigned x, unsigned line, const char *s)
{
    for (; *s; ++s, x += 6)
        glyph(x, line, *s);
    return x + 6;
}

static void hex(unsigned x, unsigned line, uint32_t value)
{
    for (unsigned i = 0; i < 8; ++i) {
        unsigned d = (value >> (28 - 4 * i)) & 15u;
        glyph(x + 6 * i, line, (char)(d < 10 ? '0' + d : 'A' + d - 10));
    }
}

/* Every wait is bounded, and after one wait runs out the port is given up, so a port that never drains cannot hold the
   processor for long. */
static int port_dead;

static void send(uint32_t byte)
{
    uint32_t n = 0;
    while (!port_dead && (SPI_FSR & 0x1Fu) >= 12u)
        if (++n == 200000u)
            port_dead = 1;
    if (!port_dead)
        SPI_TDR = byte;
}

/* Until everything queued has left the shifter: the data/command pin must not move before that. */
static void drain(void)
{
    uint32_t n = 0;
    while (!port_dead && ((SPI_FSR & 0x1Fu) || (SPI_SR & (1u << 24))))
        if (++n == 400000u)
            port_dead = 1;
}

static void show(void)
{
    uint32_t der = SPI_DER, tcr = SPI_TCR;
    SPI_DER = 0;                                   /* the firmware's DMA requests off */
    SPI_CR = (SPI_CR & 1u) | 0x300u;               /* keep the module on, empty both FIFOs */
    SPI_SR = 0x3F00u;                              /* clear the sticky flags */
    SPI_TCR = (tcr & 0xFF000000u) | (1u << 19) | 7u; /* the port's own clock mode and chip select, 8-bit frames, receive masked */
    drain();
    DC_CLEAR = DC_PIN;                             /* commands: columns 0-127, pages 0-7 */
    send(0x21); send(0); send(127); send(0x22); send(0); send(7);
    drain();
    DC_SET = DC_PIN;                               /* data */
    for (unsigned i = 0; i < 1024u; ++i)
        send(screen[i]);
    drain();
    SPI_TCR = tcr;                                 /* as found: a test call leaves the port usable */
    SPI_DER = der;
}

/* kind is the exception number: 3 HardFault, 4 MemManage, 5 BusFault, 6 UsageFault. */
void fault_screen_report(uint32_t kind, uint32_t pc, uint32_t lr)
{
    uint32_t cfsr = CFSR;
    port_dead = 0;
    for (unsigned i = 0; i < sizeof screen; ++i)
        screen[i] = 0;
    text(1, 0, "404LAB FAULT SCREEN");
    for (unsigned x = 0; x < 128; ++x)
        screen[128 + x] |= 1u;                     /* a rule under the title */
    text(1, 2, kind == 3 ? "HARD FAULT" : kind == 4 ? "MEMORY FAULT" : kind == 5 ? "BUS FAULT" : kind == 6 ? "USAGE FAULT" : "FAULT");
    hex(text(1, 3, "PC"), 3, pc);
    hex(text(1, 4, "LR"), 4, lr);
    hex(text(1, 5, "CFSR"), 5, cfsr);
    /* The address that was accessed, when the processor kept one; else the hard fault status. */
    hex(text(1, 6, cfsr & 0x8000u ? "BFAR" : cfsr & 0x80u ? "MMFAR" : "HFSR"), 6, cfsr & 0x8000u ? BFAR : cfsr & 0x80u ? MMFAR : HFSR);
    text(1, 7, "PHOTO THIS, POWER OFF");
    show();
    fault_screen_shown++;
}

/* The vector target. The frame is on whichever stack was in use (EXC_RETURN bit 2): PC at +24, LR at +20. */
__attribute__((naked)) void fault_screen_fault(void)
{
    __asm__ volatile(
        "tst lr, #4\n"
        "ite eq\n"
        "mrseq r3, msp\n"
        "mrsne r3, psp\n"
        "ldr r1, [r3, #24]\n"
        "ldr r2, [r3, #20]\n"
        "mrs r0, ipsr\n"
        "ldr r3, 1f\n"
        "mov sp, r3\n"
        "bl fault_screen_report\n"
        "2: b 2b\n"
        ".p2align 2\n"
        "1: .word fault_screen_stack + 1024\n");
}

static int hold_is_down;

/* Runs in the panel path for every key event; only watches, so the firmware still gets each event. */
void fault_screen_on_event(void *owner, const struct event *event)
{
    (void)owner;
    if (event->code == HOLD && (event->type == KEY_DOWN || event->type == KEY_UP))
        hold_is_down = event->type == KEY_DOWN;
    else if (event->code == ROLL && event->type == KEY_DOWN && hold_is_down && CURRENT_PAGE == MAIN_PAGE)
        __asm__ volatile("udf #0");                /* a fault on purpose */
}
