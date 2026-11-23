/* On the main screen, HOLD + ROLL opens Roland's SYSTEM screen. Every event still goes on to the firmware unchanged: this only watches. Runs in the panel path.
   Everywhere else these keys stay the firmware's own, because that is the only place they were checked to be free. */
enum { KEY_DOWN = 5, KEY_UP = 6, HOLD = 0x11, ROLL = 0x21, MAIN_PAGE = 1, SYSTEM_PAGE = 53 };

#define CURRENT_PAGE (*(volatile unsigned short *)0x80245880) /* stock 5.52 and DOOM OS 0.7.3 and 0.7.4 */

struct event { short type, code, value; };

void request_page(int page);

static int hold_is_down;
volatile unsigned quick_system_opened;

void quick_system_on_event(void *owner, const struct event *event)
{
    (void)owner;
    if (event->code == HOLD && (event->type == KEY_DOWN || event->type == KEY_UP)) {
        hold_is_down = event->type == KEY_DOWN;
    } else if (event->code == ROLL && event->type == KEY_DOWN && hold_is_down && CURRENT_PAGE == MAIN_PAGE) {
        quick_system_opened++;
        request_page(SYSTEM_PAGE);
    }
}
