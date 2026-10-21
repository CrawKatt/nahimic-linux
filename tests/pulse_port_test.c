/* Exercise the actual Pulse callback without opening an audio device. */
#define main pulse_reader_main
#include "../host/pulse_state.c"
#undef main
#include <assert.h>

int main(void) {
    struct apo_volume_shared memory = {0};
    struct apo_volume_state observed;
    pa_sink_port_info port = {0};
    pa_sink_info sink = {0};
    loop = pa_mainloop_new();
    assert(loop);
    shared = &memory;
    target = "speaker";
    strcpy(current.target, target);
    current.magic = APO_VOLUME_MAGIC;
    sink.name = target;
    sink.index = 10;
    sink.flags = PA_SINK_DECIBEL_VOLUME;
    pa_channel_map_init_stereo(&sink.channel_map);
    pa_cvolume_set(&sink.volume, 2, PA_VOLUME_NORM / 2);
    sink.active_port = &port;
    const char *speakers[] = {"[Out] Speaker", "analog-output-speaker"};
    const char *other_ports[] = {"[Out] Headphones", "analog-output-headphones", "hdmi-output-0", NULL};
    for(unsigned i=0;i<2;++i) {
        expected_port = speakers[i];
        for(unsigned j=0;j<4;++j) {
            failed = ready = 0;
            port.name = expected_port;
            sink.active_port = &port;
            info(NULL, &sink, 0, NULL);
            assert(ready && !failed && apo_volume_snapshot(shared, &observed) && observed.valid);
            sink.mute = !sink.mute;
            info(NULL, &sink, 0, NULL);
            assert(!failed && apo_volume_snapshot(shared, &observed) && observed.muted == (uint32_t)sink.mute);
            port.name = other_ports[j];
            if(!port.name)sink.active_port = NULL;
            info(NULL, &sink, 0, NULL);
            assert(failed && apo_volume_snapshot(shared, &observed) && !observed.valid);
        }
    }
    pa_mainloop_free(loop);
    puts("speaker port changes invalidate the APO state; mute changes preserve it: passed");
    return 0;
}
