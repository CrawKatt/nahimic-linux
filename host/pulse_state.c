/* Read the selected native sink; publish its actual state for the APO host. */
#define _POSIX_C_SOURCE 200809L
#include <pulse/pulseaudio.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "volume_state.h"

_Static_assert(sizeof(struct apo_volume_state)==296,"volume payload ABI");
_Static_assert(sizeof(struct apo_volume_shared)==600,"volume mapping ABI");
static pa_mainloop *loop;
static struct apo_volume_shared *shared;
static struct apo_volume_state current;
static const char *target;
static const char *expected_port;
static uint32_t sink_index=PA_INVALID_INDEX;
static int failed, ready;
static volatile sig_atomic_t stopping;

static void publish(void) {
    struct timespec now;
    clock_gettime(CLOCK_REALTIME,&now);
    current.timestamp_100ns=116444736000000000ULL+(uint64_t)now.tv_sec*10000000ULL+now.tv_nsec/100;
    apo_volume_publish(shared, &current);
}

static void fail(const char *message) {
    fprintf(stderr,"volume_state_error: %s\n",message);
    failed=1;current.valid=0;publish();pa_mainloop_quit(loop,1);
}

static void info(pa_context *context,const pa_sink_info *sink,int eol,void *userdata) {
    (void)context;(void)userdata;
    if(eol<0){fail("selected sink query failed");return;}
    if(eol>0){if(!ready)fail("selected sink is absent");return;}
    if(expected_port && (!sink->active_port || strcmp(sink->active_port->name,expected_port))) {
        fail("selected speaker port is no longer active");return;
    }
    if(strcmp(sink->name,target) || sink->volume.channels!=2 ||
       sink->channel_map.map[0]!=PA_CHANNEL_POSITION_FRONT_LEFT ||
       sink->channel_map.map[1]!=PA_CHANNEL_POSITION_FRONT_RIGHT ||
       !(sink->flags & PA_SINK_DECIBEL_VOLUME)) {
        fail("selected sink does not expose the required stereo dB volume");return;
    }
    sink_index=sink->index;
    current.channels=2;current.muted=!!sink->mute;
    current.master_db=(float)pa_sw_volume_to_dB(pa_cvolume_max(&sink->volume));
    current.channel_db[0]=(float)pa_sw_volume_to_dB(sink->volume.values[0]);
    current.channel_db[1]=(float)pa_sw_volume_to_dB(sink->volume.values[1]);
    current.valid=1;publish();
    fprintf(stderr,"volume_state mute=%u db=%.9g left=%.9g right=%.9g\n",
            current.muted,current.master_db,current.channel_db[0],current.channel_db[1]);
    if(!ready){ready=1;fprintf(stderr,"volume_state_ready target=%s\n",target);}
    fflush(stderr);
}

static void query(pa_context *context) {
    pa_operation *op=pa_context_get_sink_info_by_name(context,target,info,NULL);
    if(!op){fail("cannot request selected sink state");return;}
    pa_operation_unref(op);
}

static void changed(pa_context *context,pa_subscription_event_type_t event,uint32_t index,void *userdata) {
    (void)userdata;
    if((event & PA_SUBSCRIPTION_EVENT_FACILITY_MASK)!=PA_SUBSCRIPTION_EVENT_SINK || index!=sink_index)return;
    if((event & PA_SUBSCRIPTION_EVENT_TYPE_MASK)==PA_SUBSCRIPTION_EVENT_REMOVE){fail("selected sink removed");return;}
    query(context);
}

static void subscribed(pa_context *context,int success,void *userdata) {
    (void)userdata;
    if(!success){fail("sink subscription failed");return;}
    query(context);
}

static void connection(pa_context *context,void *userdata) {
    (void)userdata;
    switch(pa_context_get_state(context)) {
    case PA_CONTEXT_READY: {
        pa_context_set_subscribe_callback(context,changed,NULL);
        pa_operation *op=pa_context_subscribe(context,PA_SUBSCRIPTION_MASK_SINK,subscribed,NULL);
        if(!op){fail("cannot subscribe to sink events");break;}
        pa_operation_unref(op);break;
    }
    case PA_CONTEXT_FAILED: case PA_CONTEXT_TERMINATED: fail("Pulse connection lost");break;
    default:break;
    }
}

static void tick(pa_mainloop_api *api,pa_time_event *event,const struct timeval *when,void *userdata) {
    (void)when;(void)userdata;
    if(stopping){pa_mainloop_quit(loop,0);return;}
    if(ready && !failed)publish();
    struct timeval next;gettimeofday(&next,NULL);pa_timeval_add(&next,200000);
    api->time_restart(event,&next);
}

static void stop(int signum){(void)signum;stopping=1;}

int main(int argc,char **argv) {
    if((argc!=3 && argc!=4) || argv[2][0]!='/' || strlen(argv[1])>=sizeof(current.target)){
        fprintf(stderr,"usage: pulse_state EXACT_SINK /absolute/new/state-file [EXPECTED_PORT]\n");return 2;
    }
    expected_port=argc==4?argv[3]:NULL;
    target=argv[1];strcpy(current.target,target);current.magic=APO_VOLUME_MAGIC;
    int fd=open(argv[2],O_CREAT|O_EXCL|O_RDWR,0600);
    if(fd<0){perror("state file");return 1;}
    if(ftruncate(fd,sizeof(*shared))){perror("state size");close(fd);return 1;}
    shared=mmap(NULL,sizeof(*shared),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);
    if(shared==MAP_FAILED){perror("state mapping");return 1;}
    loop=pa_mainloop_new();pa_mainloop_api *api=pa_mainloop_get_api(loop);
    pa_context *context=pa_context_new(api,"Nahimic native endpoint state");
    if(!context){fprintf(stderr,"Pulse context allocation failed\n");return 1;}
    pa_context_set_state_callback(context,connection,NULL);
    signal(SIGTERM,stop);signal(SIGINT,stop);
    struct timeval next;gettimeofday(&next,NULL);pa_timeval_add(&next,200000);
    pa_time_event *timer=api->time_new(api,&next,tick,NULL);
    if(pa_context_connect(context,NULL,PA_CONTEXT_NOAUTOSPAWN,NULL)<0)fail("Pulse connect failed");
    int result=1;
    if(!failed)pa_mainloop_run(loop,&result);
    current.valid=0;publish();
    api->time_free(timer);pa_context_set_state_callback(context,NULL,NULL);
    pa_context_disconnect(context);pa_context_unref(context);pa_mainloop_free(loop);
    munmap(shared,sizeof(*shared));return failed?1:result;
}
