/* Counts calls of the hooked function. Runs inside the audio path: no allocation, no files, no waiting. */
volatile unsigned demo_counter_calls;

void demo_counter_hook(void)
{
    demo_counter_calls++;
}
