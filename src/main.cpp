// VoiceDJ - CS Voice Chat Modulator
// A high-performance C++ replacement for the Python Voice-Chat-DJ
// Built with: miniaudio, SoundTouch, Dear ImGui, Windows SAPI
// Requires: VB-Audio Virtual Cable (free download)

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mutex>
#include <thread>
#include <atomic>
#include <deque>
#include <windowsx.h>
#include <shellapi.h>
#include <shlobj.h>
#include <commdlg.h>
#include <d3d11.h>
#include <dxgi.h>
#include <tchar.h>
#include <string>
#include <vector>
#include <functional>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <sstream>
#include <filesystem>
#include <map>
#include <memory>
#include <chrono>

// ─── Single-header audio decoders ────────────────────────────────────────────
#define DR_MP3_IMPLEMENTATION
#define DR_MP3_FLOAT_OUTPUT
#include "dr_mp3.h"

#define DR_WAV_IMPLEMENTATION
#include "dr_wav.h"

// ─── miniaudio ───────────────────────────────────────────────────────────────
#define MINIAUDIO_IMPLEMENTATION
#include "../libs/miniaudio.h"

// ─── SoundTouch ──────────────────────────────────────────────────────────────
#include "../libs/soundtouch/include/SoundTouch.h"

// ─── Dear ImGui ──────────────────────────────────────────────────────────────
#include "../libs/imgui/imgui.h"
#include "../libs/imgui/backends/imgui_impl_win32.h"
#include "../libs/imgui/backends/imgui_impl_dx11.h"

// ─── Forward declarations ─────────────────────────────────────────────────────
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);

// ─── Constants ───────────────────────────────────────────────────────────────
static const int SAMPLE_RATE     = 48000;
static const int CHANNELS        = 2;
static const int FRAME_SIZE      = 480;
static const float PI_F          = 3.14159265358979323846f;
static const int FFT_SIZE        = 2048;
static const int SPEC_BINS       = FFT_SIZE / 2;

// ─── App Version ─────────────────────────────────────────────────────────────
static const char* APP_VERSION = "2.12.0";
static const char* APP_NAME    = "VoiceDJ for CS";

// ─── Structs ─────────────────────────────────────────────────────────────────
struct Complex { float r, i; };

struct MusicEntry {
    std::string name;
    std::string path;
};

struct AppSettings {
    int   inputDeviceIndex   = -1;
    int   outputDeviceIndex  = -1;
    int   listenDeviceIndex  = -1;
    bool  listenEnabled      = false;  // legacy, kept for compat
    float musicVolume        = 1.0f;
    float micVolume          = 1.0f;
    float masterVolume       = 1.0f;
    int   micMode            = 2;   // 0=Off, 1=Always On, 2=PTT
    bool  pitchEnabled       = false;
    float pitchSemitones     = 0.0f;
    bool  reverbEnabled      = false;
    float reverbDecay        = 0.5f;
    float reverbMix          = 0.3f;
    bool  robotEnabled       = false;
    bool  noiseGateEnabled   = false;
    float noiseGateThreshold = 0.02f;
    bool  eqEnabled          = false;
    float eqLow              = 0.0f;
    float eqMid              = 0.0f;
    float eqHigh             = 0.0f;
    int   ttsVoiceIndex      = 0;
    float ttsRate            = 1.0f;
    float ttsVolume          = 1.0f;
    bool  loopEnabled        = false;
    // Monitor voice/music separately
    bool  listenVoiceEnabled = false;
    bool  listenMusicEnabled = false;
    int   listenVoiceDeviceIndex = -1;
    int   listenMusicDeviceIndex = -1;
    // Echo
    bool  echoEnabled       = false;
    float echoDelay         = 0.25f;  // seconds
    float echoFeedback      = 0.4f;
    float echoMix           = 0.5f;
    // Apply effects to hotkey sound clips
    bool  effectsOnClips    = false;
    // Apply effects to music/sound effects playback
    bool  effectsOnMusic    = false;
    // Stackable audio: hotkey clips mix instead of replacing current audio
    bool  stackableAudio    = false;
    // Music-specific effects chain (independent of mic effects)
    bool  mPitchEnabled     = false;
    float mPitchSemitones   = 0.0f;
    bool  mReverbEnabled    = false;
    float mReverbDecay      = 0.5f;
    float mReverbMix        = 0.3f;
    bool  mEchoEnabled      = false;
    float mEchoDelay        = 0.25f;
    float mEchoFeedback     = 0.4f;
    float mEchoMix          = 0.5f;
    bool  mRobotEnabled     = false;
    bool  mEqEnabled        = false;
    float mEqLow            = 0.0f;
    float mEqMid            = 0.0f;
    float mEqHigh           = 0.0f;
    // Music speed (tempo change)
    bool  mSpeedEnabled     = false;
    float mSpeedPercent     = 100.0f;  // 50 to 150 percent (100 = normal speed)
    std::map<int, std::string> binds;
};

enum class PlayState { Stopped, Playing, Paused };

// ─── FFT ─────────────────────────────────────────────────────────────────────
static void doFFT(Complex* x, int n) {
    for (int i=1,j=0; i<n; i++) {
        int bit=n>>1;
        for (; j&bit; bit>>=1) j^=bit;
        j^=bit;
        if (i<j) std::swap(x[i],x[j]);
    }
    for (int len=2; len<=n; len<<=1) {
        float ang=-2.0f*PI_F/len;
        Complex wlen={cosf(ang),sinf(ang)};
        for (int i=0; i<n; i+=len) {
            Complex w={1.0f,0.0f};
            for (int j=0; j<len/2; j++) {
                Complex u=x[i+j];
                Complex v={x[i+j+len/2].r*w.r-x[i+j+len/2].i*w.i,
                           x[i+j+len/2].r*w.i+x[i+j+len/2].i*w.r};
                x[i+j]={u.r+v.r,u.i+v.i};
                x[i+j+len/2]={u.r-v.r,u.i-v.i};
                float wr=w.r*wlen.r-w.i*wlen.i;
                float wi=w.r*wlen.i+w.i*wlen.r;
                w={wr,wi};
            }
        }
    }
}

// ─── Reverb ──────────────────────────────────────────────────────────────────
struct CombFilter {
    std::vector<float> buf; int pos=0; float feedback=0.5f,damp=0.3f,store=0.0f;
    void init(int d,float fb){buf.assign(d,0.0f);pos=0;feedback=fb;}
    float process(float in){
        float out=buf[pos];
        store=out*(1.0f-damp)+store*damp;
        buf[pos]=in+store*feedback;
        pos=(pos+1)%(int)buf.size();
        return out;
    }
};
struct AllpassFilter {
    std::vector<float> buf; int pos=0;
    void init(int d){buf.assign(d,0.0f);pos=0;}
    float process(float in){
        float bo=buf[pos],out=-in+bo;
        buf[pos]=in+bo*0.5f;
        pos=(pos+1)%(int)buf.size();
        return out;
    }
};
struct Reverb {
    CombFilter   combs[4];
    AllpassFilter aps[2];
    float mix=0.3f,decay=0.5f;
    void init(int sr){
        int cd[]={(int)(0.0297f*sr),(int)(0.0371f*sr),(int)(0.0411f*sr),(int)(0.0437f*sr)};
        for(int i=0;i<4;i++) combs[i].init(cd[i],decay);
        int ad[]={(int)(0.005f*sr),(int)(0.0017f*sr)};
        for(int i=0;i<2;i++) aps[i].init(ad[i]);
    }
    void setDecay(float d){decay=d;for(int i=0;i<4;i++)combs[i].feedback=d;}
    float process(float in){
        float out=0;
        for(int i=0;i<4;i++) out+=combs[i].process(in);
        out/=4;
        for(int i=0;i<2;i++) out=aps[i].process(out);
        return (1.0f-mix)*in+mix*out;
    }
};

// ─── Biquad EQ ───────────────────────────────────────────────────────────────
struct Biquad {
    float b0=1,b1=0,b2=0,a1=0,a2=0,x1=0,x2=0,y1=0,y2=0;
    void lowShelf(float f,float gdB,int sr){
        float A=powf(10.0f,gdB/40.0f),w=2*PI_F*f/sr,c=cosf(w),s=sinf(w);
        float al=s/2*sqrtf((A+1/A)*(1/1.0f-1)+2);
        float a0=(A+1)+(A-1)*c+2*sqrtf(A)*al;
        b0=A*((A+1)-(A-1)*c+2*sqrtf(A)*al)/a0;
        b1=2*A*((A-1)-(A+1)*c)/a0;
        b2=A*((A+1)-(A-1)*c-2*sqrtf(A)*al)/a0;
        a1=-2*((A-1)+(A+1)*c)/a0;
        a2=((A+1)+(A-1)*c-2*sqrtf(A)*al)/a0;
    }
    void peaking(float f,float gdB,float Q,int sr){
        float A=powf(10.0f,gdB/40.0f),w=2*PI_F*f/sr,al=sinf(w)/(2*Q);
        float a0=1+al/A;
        b0=(1+al*A)/a0;b1=(-2*cosf(w))/a0;b2=(1-al*A)/a0;
        a1=(-2*cosf(w))/a0;a2=(1-al/A)/a0;
    }
    void highShelf(float f,float gdB,int sr){
        float A=powf(10.0f,gdB/40.0f),w=2*PI_F*f/sr,c=cosf(w),s=sinf(w);
        float al=s/2*sqrtf((A+1/A)*(1/1.0f-1)+2);
        float a0=(A+1)-(A-1)*c+2*sqrtf(A)*al;
        b0=A*((A+1)+(A-1)*c+2*sqrtf(A)*al)/a0;
        b1=-2*A*((A-1)+(A+1)*c)/a0;
        b2=A*((A+1)+(A-1)*c-2*sqrtf(A)*al)/a0;
        a1=2*((A-1)-(A+1)*c)/a0;
        a2=((A+1)-(A-1)*c-2*sqrtf(A)*al)/a0;
    }
    float process(float in){
        float out=b0*in+b1*x1+b2*x2-a1*y1-a2*y2;
        x2=x1;x1=in;y2=y1;y1=out;return out;
    }
    void reset(){x1=x2=y1=y2=0;}
};

// ─── Noise Gate ──────────────────────────────────────────────────────────────
struct NoiseGate {
    float threshold=0.02f,gain=0.0f;
    float process(float in){
        float l=fabsf(in);
        float ac=expf(-1.0f/(SAMPLE_RATE*0.005f));
        float rc=expf(-1.0f/(SAMPLE_RATE*0.05f));
        gain=(l>threshold)?gain*ac+(1-ac):gain*rc;
        return in*gain;
    }
};

// ─── Robot Voice ─────────────────────────────────────────────────────────────
struct RobotVoice {
    float phase=0,freq=80.0f;
    std::vector<float> cb; int cp=0;
    void init(){int d=SAMPLE_RATE/80;cb.assign(d,0.0f);}
    float process(float in){
        float carrier=sinf(2*PI_F*phase);
        phase+=freq/SAMPLE_RATE; if(phase>1)phase-=1;
        float mod=in*carrier;
        float co=cb[cp];
        cb[cp]=mod+co*0.7f;
        cp=(cp+1)%(int)cb.size();
        return 0.4f*in+0.6f*co;
    }
};

// ─── Echo (multi-tap delay) ───────────────────────────────────────────────────
struct Echo {
    std::vector<float> bufL, bufR;
    int pos=0;
    float feedback=0.4f, mix=0.5f;
    int delayFrames=SAMPLE_RATE/4; // 250ms default

    void init(){ bufL.assign(SAMPLE_RATE*4,0.0f); bufR.assign(SAMPLE_RATE*4,0.0f); pos=0; }
    void setDelay(float seconds){ delayFrames=(int)(seconds*SAMPLE_RATE); if(delayFrames<1)delayFrames=1; if(delayFrames>=(int)bufL.size())delayFrames=(int)bufL.size()-1; }
    std::pair<float,float> process(float inL, float inR){
        int readPos=(pos-delayFrames+(int)bufL.size())%(int)bufL.size();
        float echoL=bufL[readPos], echoR=bufR[readPos];
        bufL[pos]=inL+echoL*feedback;
        bufR[pos]=inR+echoR*feedback;
        pos=(pos+1)%(int)bufL.size();
        return {inL*(1-mix)+echoL*mix, inR*(1-mix)+echoR*mix};
    }
};

// ─── Global State ─────────────────────────────────────────────────────────────────────────────────
static AppSettings g_settings;
static ma_context  g_maCtx;
static ma_device   g_outDev, g_capDev;
static bool        g_outDevInit=false, g_capDevInit=false;

// Monitor Voice device (hears mic through speakers)
static ma_device   g_monVoiceDev;
static bool        g_monVoiceDevInit=false;
static std::mutex         g_monVoiceMtx;
static std::deque<float>  g_monVoiceBuf;
static const size_t       MON_VOICE_MAX=SAMPLE_RATE*CHANNELS*2;

// Monitor Music device (hears music/output through speakers)
static ma_device   g_monMusicDev;
static bool        g_monMusicDevInit=false;
static std::mutex         g_monMusicMtx;
static std::deque<float>  g_monMusicBuf;
static const size_t       MON_MUSIC_MAX=SAMPLE_RATE*CHANNELS*2;

static std::vector<std::string> g_inputDevNames, g_outputDevNames;
static ma_device_info *g_pPlaybackInfos=nullptr, *g_pCaptureInfos=nullptr;
static ma_uint32        g_playbackCount=0, g_captureCount=0;

// Music
static std::mutex         g_musicMtx;
static std::vector<float> g_musicBuf;
static size_t             g_musicPos=0;
static bool               g_musicLoaded=false;
static std::atomic<PlayState> g_playState{PlayState::Stopped};
static std::vector<MusicEntry> g_musicList;
static int                g_selectedTrack=-1;
static int                g_bindTrack[10];

// Mic ring buffer
static std::mutex         g_ringMtx;
static std::deque<float>  g_ringBuf;
static const size_t       RING_MAX=SAMPLE_RATE*CHANNELS*2;

// Effects (mic chain)
static soundtouch::SoundTouch g_st;
static Reverb     g_reverb;
static RobotVoice g_robot;
static NoiseGate  g_gate;
static Biquad     g_eqL, g_eqM, g_eqH;
static Echo       g_echo;
// Effects (music chain - independent instances)
static soundtouch::SoundTouch g_mSt;
static Reverb     g_mReverb;
static RobotVoice g_mRobot;
static Biquad     g_mEqL, g_mEqM, g_mEqH;
static Echo       g_mEcho;
// SoundTouch persistent output queue for music chain
// Samples are fed in continuously; output is drained here and consumed by playbackCallback
static std::deque<float> g_mStOutBuf;  // processed output samples ready to play
static bool              g_mStActive=false; // true when pitch or speed is enabled
// Stackable clips: each entry is {buffer, position}
struct ClipInstance { std::vector<float> buf; size_t pos=0; };
static std::mutex              g_clipStackMtx;
static std::vector<ClipInstance> g_clipStack;
// Panel splitter state
static float g_leftPanelW = 320.0f;
static float g_effPanelH  = 220.0f;  // mic effects child height
static float g_meffPanelH = 240.0f;  // music effects child height

// Spectrum
static std::mutex         g_specMtx;
static float              g_specData[SPEC_BINS]={};
static float              g_specSmooth[SPEC_BINS]={};
static std::deque<float>  g_fftIn;
static Complex            g_fftBuf[FFT_SIZE];

// Clip vs music tracking
static std::atomic<bool> g_isClipPlaying{false}; // true when a hotkey clip is playing
// Echo tail drain: when source ends, keep playing for echoDelay seconds to let echo ring out
static std::atomic<bool> g_draining{false};  // true while draining echo tail
static std::atomic<int>  g_drainFrames{0};   // frames remaining in drain

// UI state
static bool g_showTTSPopup=false;
static char g_ttsText[1024]={};
static bool g_showBindPopup=false;
static int  g_bindSlot=-1;
static char g_statusMsg[256]="Ready. Select devices and press Start.";
static bool g_devicesStarted=false;
static bool g_pttActive=false;

// PTT polling thread
static std::thread g_pttThread;
static std::atomic<bool> g_pttRunning{false};

// Notification popup
static std::string g_notifText;
static float       g_notifTimer=0.0f;

// YouTube download state
static char  g_ytUrl[512]={};
static bool  g_ytDownloading=false;
static std::string g_ytStatus;
static std::thread g_ytThread;
static std::string g_musicDirGlobal;  // set in WinMain, used by YT callback

// Global HWND (needed for TTS bring-to-front)
static HWND g_hwnd=nullptr;

// ─── TTS State Machine ────────────────────────────────────────────────────────
// FIX #1: Completely reworked TTS state machine.
// The popup is now a persistent window that stays open and functional.
// It is NOT closed when rendering starts. Buttons are disabled during render.
// The window close button works correctly in all states.
// Ctrl+Tab only opens the TTS window (not the main window) when already open.

static std::string g_lastTtsWavPath;
enum class TTSState { Idle, Rendering, Done, Error };
static std::atomic<TTSState> g_ttsState{TTSState::Idle};
static std::thread g_ttsThread;
static std::string g_ttsPendingWav;    // set by bg thread when done
static std::string g_ttsSaveFilename;  // sanitized text used as save filename
static bool  g_ttsSaveToLib=false;     // true if save-to-library was requested
static bool  g_ttsSaveAndPlay=false;   // true if save-to-library AND play was requested
static bool  g_ttsJustOpened=false;    // true on first frame popup opens (for bring-to-front)
static HWND  g_ttsFakeHwnd=nullptr;    // separate HWND for TTS popup (fixes Ctrl+Tab bringing both)

// ─── Audio Callbacks ──────────────────────────────────────────────────────────
static void captureCallback(ma_device* pDev, void* pOut, const void* pIn, ma_uint32 frames) {
    if (!pIn) return;
    bool active=false;
    switch(g_settings.micMode){
        case 1: active=true; break;
        case 2: active=g_pttActive; break;
        default: active=false;
    }
    if (!active) return;

    const float* in=(const float*)pIn;
    int inCh=(int)pDev->capture.channels;
    std::vector<float> buf(frames*CHANNELS);

    for (ma_uint32 f=0;f<frames;f++){
        float L=in[f*inCh];
        float R=(inCh>1)?in[f*inCh+1]:L;

        if(g_settings.noiseGateEnabled){L=g_gate.process(L);R=g_gate.process(R);}
        if(g_settings.eqEnabled){
            L=g_eqL.process(L);L=g_eqM.process(L);L=g_eqH.process(L);
            R=g_eqL.process(R);R=g_eqM.process(R);R=g_eqH.process(R);
        }
        if(g_settings.reverbEnabled){L=g_reverb.process(L);R=g_reverb.process(R);}
        if(g_settings.robotEnabled){L=g_robot.process(L);R=g_robot.process(R);}
        if(g_settings.echoEnabled){
            auto [eL,eR]=g_echo.process(L,R);
            L=eL; R=eR;
        }

        float vol=g_settings.micVolume*g_settings.masterVolume;
        buf[f*2+0]=std::max(-1.0f,std::min(1.0f,L*vol));
        buf[f*2+1]=std::max(-1.0f,std::min(1.0f,R*vol));
    }

    // Pitch shift
    if(g_settings.pitchEnabled && fabsf(g_settings.pitchSemitones)>0.01f){
        g_st.putSamples(buf.data(),frames);
        std::vector<float> pitched(frames*CHANNELS);
        int got=(int)g_st.receiveSamples(pitched.data(),frames);
        if(got>0) buf.assign(pitched.begin(),pitched.begin()+got*CHANNELS);
    }

    {std::lock_guard<std::mutex> lk(g_ringMtx);
     for(float s:buf) if(g_ringBuf.size()<RING_MAX) g_ringBuf.push_back(s);}

    // NOTE: Voice monitor is fed exclusively by rawCaptureCallback (always-on).
    // captureCallback only feeds the virtual mic (PTT-gated). Do NOT double-feed here.

    // Feed spectrum
    {std::lock_guard<std::mutex> lk(g_specMtx);
     for(ma_uint32 f=0;f<frames;f++){g_fftIn.push_back(buf[f*2]);
         while((int)g_fftIn.size()>FFT_SIZE)g_fftIn.pop_front();}}
}

// FIX #4 (continued): The capture callback above only runs when PTT is active (for virtual mic).
// But monitor voice should hear mic even when PTT is inactive.
// We need a separate always-on capture path for monitor voice.
// Solution: use a second capture device for monitor, OR feed monitor from a raw capture callback.
// We implement this with a dedicated "raw mic" capture device for monitor voice.
static ma_device   g_rawCapDev;
static bool        g_rawCapDevInit=false;

// Monitor-specific effects instances (separate from main mic chain to avoid thread conflicts)
static soundtouch::SoundTouch g_monSt;
static Echo   g_monEcho;
static Reverb g_monReverb;
static RobotVoice g_monRobot;
static void rawCaptureCallback(ma_device* pDev, void* pOut, const void* pIn, ma_uint32 frames) {
    // Always-on capture for voice monitor. Applies full mic effects so user hears their processed voice.
    if (!pIn) return;
    if (!g_monVoiceDevInit || !g_settings.listenVoiceEnabled) return;
    const float* in=(const float*)pIn;
    int inCh=(int)pDev->capture.channels;
    // Apply the same effects chain as captureCallback
    std::vector<float> buf(frames*CHANNELS);
    float vol=g_settings.micVolume*g_settings.masterVolume;
    for (ma_uint32 f=0;f<frames;f++){
        float L=in[f*inCh];
        float R=(inCh>1)?in[f*inCh+1]:L;
        if(g_settings.noiseGateEnabled){L=g_gate.process(L);R=g_gate.process(R);}
        if(g_settings.eqEnabled){
            L=g_eqL.process(L);L=g_eqM.process(L);L=g_eqH.process(L);
            R=g_eqL.process(R);R=g_eqM.process(R);R=g_eqH.process(R);
        }
        if(g_settings.reverbEnabled){L=g_monReverb.process(L);R=g_monReverb.process(R);}
        if(g_settings.robotEnabled){L=g_monRobot.process(L);R=g_monRobot.process(R);}
        if(g_settings.echoEnabled){
            auto [eL,eR]=g_monEcho.process(L,R); L=eL; R=eR;
        }
        buf[f*2+0]=std::max(-1.0f,std::min(1.0f,L*vol));
        buf[f*2+1]=std::max(-1.0f,std::min(1.0f,R*vol));
    }
    // Pitch shift for monitor
    if(g_settings.pitchEnabled && fabsf(g_settings.pitchSemitones)>0.01f){
        g_monSt.putSamples(buf.data(),frames);
        std::vector<float> pitched(frames*CHANNELS);
        int got=(int)g_monSt.receiveSamples(pitched.data(),frames);
        if(got>0) buf.assign(pitched.begin(),pitched.begin()+got*CHANNELS);
    }
    // Cap buffer to ~20ms to prevent delay buildup
    static const size_t MON_VOICE_TIGHT = SAMPLE_RATE*CHANNELS/50; // 20ms
    static const size_t MON_VOICE_DROP  = SAMPLE_RATE*CHANNELS/100; // 10ms
    std::lock_guard<std::mutex> lk(g_monVoiceMtx);
    while(g_monVoiceBuf.size() > MON_VOICE_DROP) g_monVoiceBuf.pop_front();
    for(float s:buf)
        if(g_monVoiceBuf.size()<MON_VOICE_TIGHT) g_monVoiceBuf.push_back(s);
}

static void playbackCallback(ma_device* pDev, void* pOut, const void* pIn, ma_uint32 frames) {
    float* out=(float*)pOut;
    size_t needed=frames*CHANNELS;
    std::vector<float> mixed(needed,0.0f);
    // musicOnly holds music/clips BEFORE mic is mixed in (for monitor music)
    std::vector<float> musicOnly(needed,0.0f);

    // Helper: apply music effects chain to a stereo sample pair
    auto applyMusicFx=[&](float& L, float& R){
        if(g_settings.mEqEnabled){
            L=g_mEqL.process(L);L=g_mEqM.process(L);L=g_mEqH.process(L);
            R=g_mEqL.process(R);R=g_mEqM.process(R);R=g_mEqH.process(R);
        }
        if(g_settings.mReverbEnabled){L=g_mReverb.process(L);R=g_mReverb.process(R);}
        if(g_settings.mRobotEnabled){L=g_mRobot.process(L);R=g_mRobot.process(R);}
        if(g_settings.mEchoEnabled){
            auto [eL,eR]=g_mEcho.process(L,R); L=eL; R=eR;
        }
    };
    // Helper: apply mic effects chain to a sample pair (for hotkey clips routed through mic fx)
    auto applyMicFxToSample=[&](float& L, float& R){
        if(g_settings.noiseGateEnabled){L=g_gate.process(L);R=g_gate.process(R);}
        if(g_settings.eqEnabled){
            L=g_eqL.process(L);L=g_eqM.process(L);L=g_eqH.process(L);
            R=g_eqL.process(R);R=g_eqM.process(R);R=g_eqH.process(R);
        }
        if(g_settings.reverbEnabled){L=g_reverb.process(L);R=g_reverb.process(R);}
        if(g_settings.robotEnabled){L=g_robot.process(L);R=g_robot.process(R);}
        if(g_settings.echoEnabled){
            auto [eL,eR]=g_echo.process(L,R); L=eL; R=eR;
        }
    };
    // SoundTouch persistent queue approach:
    // Every callback, we feed the current chunk into g_mSt and drain ALL available output
    // into g_mStOutBuf. The playback loop then reads from g_mStOutBuf instead of the raw chunk.
    // This absorbs SoundTouch's startup latency transparently - output is always 100% processed.
    auto feedMusicSoundTouch=[&](const std::vector<float>& chunk, size_t frameCount){
        if(!g_mStActive || frameCount==0 || chunk.empty()) return;
        g_mSt.putSamples(chunk.data(),(uint)frameCount);
        // Drain everything available into the persistent output queue
        std::vector<float> tmp(frameCount*CHANNELS*2);
        uint got;
        while((got=(uint)g_mSt.receiveSamples(tmp.data(),(uint)frameCount))>0){
            for(uint i=0;i<got*(uint)CHANNELS;i++)
                g_mStOutBuf.push_back(tmp[i]);
        }
    };
    // Read from SoundTouch output queue (used instead of raw chunk when g_mStActive)
    auto drainMusicSoundTouchToMixed=[&](size_t needed_samples){
        // Pull up to needed_samples from the processed queue into mixed/musicOnly
        size_t n=std::min(needed_samples, g_mStOutBuf.size());
        for(size_t i=0;i<n;i++){
            float s=g_mStOutBuf.front(); g_mStOutBuf.pop_front();
            mixed[i]+=s;
            musicOnly[i]=s;
        }
    };

    // Music / clip (single-audio mode: one track at a time)
    {
     std::lock_guard<std::mutex> lk(g_musicMtx);
     if(g_playState.load()==PlayState::Playing && g_musicLoaded){
         bool isClip=g_isClipPlaying.load();
         // Both clips (effectsOnClips) and music (effectsOnMusic) use the music effects chain
         bool useClipChain=(isClip && g_settings.effectsOnClips);
         bool useMusicChain=(!isClip && g_settings.effectsOnMusic);
         bool useAnyChain=useClipChain||useMusicChain;
         // Read a chunk from the source buffer, apply music effects (reverb/echo/eq/robot)
         std::vector<float> chunk;
         size_t framesRead=0;
         for(size_t i=0;i<needed&&g_musicPos<g_musicBuf.size();i+=2,g_musicPos+=2,framesRead++){
             float L=g_musicBuf[g_musicPos]*g_settings.musicVolume*g_settings.masterVolume;
             float R=(g_musicPos+1<g_musicBuf.size())?
                 g_musicBuf[g_musicPos+1]*g_settings.musicVolume*g_settings.masterVolume:L;
             if(useAnyChain) applyMusicFx(L,R);
             chunk.push_back(L);
             chunk.push_back(R);
         }
         if(g_mStActive && useAnyChain){
             // Persistent SoundTouch queue: feed chunk in, drain output into mixed/musicOnly
             feedMusicSoundTouch(chunk,framesRead);
             drainMusicSoundTouchToMixed(needed);
         } else {
             // No pitch/speed processing: mix chunk directly
             for(size_t i=0;i<chunk.size()&&i<needed;i++){
                 mixed[i]+=chunk[i];
                 musicOnly[i]=chunk[i];
             }
         }
         if(g_musicPos>=g_musicBuf.size()){
             if(g_settings.loopEnabled){
                 g_musicPos=0;
             } else {
                 // Start drain phase: let echo tail ring out before stopping.
                 // Trigger drain if music echo is enabled (regardless of useAnyChain,
                 // since the echo buffer may have data even if effects were just enabled).
                 bool needDrain=g_settings.mEchoEnabled && g_settings.mEchoDelay>0.1f;
                 if(needDrain){
                     g_drainFrames.store((int)(g_settings.mEchoDelay*SAMPLE_RATE*CHANNELS*3.0f));
                     g_draining.store(true);
                 } else {
                     g_playState.store(PlayState::Stopped);
                     g_isClipPlaying.store(false);
                     g_draining.store(false);
                 }
             }
         }
     }
    }
    // Echo tail drain: feed silence through music effects chain to let echo ring out naturally
    if(g_draining.load()){
        int rem=g_drainFrames.load();
        if(rem>0){
            size_t drainN=std::min((size_t)frames*CHANNELS,needed);
            for(size_t i=0;i<drainN;i+=2){
                float L=0.0f,R=0.0f;
                applyMusicFx(L,R); // always use music chain during drain
                mixed[i]+=L; musicOnly[i]=L;
                if(i+1<drainN){mixed[i+1]+=R; musicOnly[i+1]=R;}
            }
            g_drainFrames.store(rem-(int)drainN);
        } else {
            g_draining.store(false);
            g_playState.store(PlayState::Stopped);
            g_isClipPlaying.store(false);
        }
    }

    // Stackable clips (mix all active clip instances)
    if(g_settings.stackableAudio){
        std::lock_guard<std::mutex> lk(g_clipStackMtx);
        for(auto& ci:g_clipStack){
            for(size_t i=0;i<needed&&ci.pos<ci.buf.size();i++,ci.pos++){
                float s=ci.buf[ci.pos]*g_settings.musicVolume*g_settings.masterVolume;
                mixed[i]+=s;
                musicOnly[i]+=s;
            }
        }
        // Remove finished clips
        g_clipStack.erase(std::remove_if(g_clipStack.begin(),g_clipStack.end(),
            [](const ClipInstance& c){return c.pos>=c.buf.size();}),g_clipStack.end());
    }

    // Mic ring (voice to virtual mic - NOT included in music monitor)
    {std::lock_guard<std::mutex> lk(g_ringMtx);
     for(size_t i=0;i<needed&&!g_ringBuf.empty();i++){
         mixed[i]+=g_ringBuf.front();g_ringBuf.pop_front();}}

    for(size_t i=0;i<needed;i++) out[i]=std::max(-1.0f,std::min(1.0f,mixed[i]));

    // Feed music monitor buffer (music/clips ONLY - no mic voice)
    if(g_monMusicDevInit && g_settings.listenMusicEnabled){
        std::lock_guard<std::mutex> lk(g_monMusicMtx);
        for(size_t i=0;i<needed;i++)
            if(g_monMusicBuf.size()<MON_MUSIC_MAX) g_monMusicBuf.push_back(musicOnly[i]);
    }

    // Feed spectrum from output
    {std::lock_guard<std::mutex> lk(g_specMtx);
     for(ma_uint32 f=0;f<frames;f++){g_fftIn.push_back(out[f*2]);
         while((int)g_fftIn.size()>FFT_SIZE)g_fftIn.pop_front();}}
}

// Monitor Voice callback: drains mic audio to speakers
static void monitorVoiceCallback(ma_device* pDev, void* pOut, const void* pIn, ma_uint32 frames) {
    float* out=(float*)pOut;
    size_t needed=frames*CHANNELS;
    std::lock_guard<std::mutex> lk(g_monVoiceMtx);
    for(size_t i=0;i<needed;i++){
        if(!g_monVoiceBuf.empty()){out[i]=g_monVoiceBuf.front();g_monVoiceBuf.pop_front();}
        else out[i]=0.0f;
    }
}

// Monitor Music callback: drains music/output audio to speakers
static void monitorMusicCallback(ma_device* pDev, void* pOut, const void* pIn, ma_uint32 frames) {
    float* out=(float*)pOut;
    size_t needed=frames*CHANNELS;
    std::lock_guard<std::mutex> lk(g_monMusicMtx);
    for(size_t i=0;i<needed;i++){
        if(!g_monMusicBuf.empty()){out[i]=g_monMusicBuf.front();g_monMusicBuf.pop_front();}
        else out[i]=0.0f;
    }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
static void updateSpectrum(){
    std::lock_guard<std::mutex> lk(g_specMtx);
    if((int)g_fftIn.size()<FFT_SIZE) return;
    for(int i=0;i<FFT_SIZE;i++){
        float w=0.5f*(1-cosf(2*PI_F*i/FFT_SIZE));
        g_fftBuf[i]={g_fftIn[i]*w,0.0f};
    }
    doFFT(g_fftBuf,FFT_SIZE);
    for(int i=0;i<SPEC_BINS;i++){
        float mag=sqrtf(g_fftBuf[i].r*g_fftBuf[i].r+g_fftBuf[i].i*g_fftBuf[i].i)/FFT_SIZE;
        float db=20*log10f(mag+1e-9f);
        float norm=(db+80)/80; norm=std::max(0.0f,std::min(1.0f,norm));
        g_specSmooth[i]=std::max(norm,g_specSmooth[i]*0.88f);
        g_specData[i]=g_specSmooth[i];
    }
}

static void resampleAndConvert(const std::vector<float>& raw,int srcCh,int srcSr){
    size_t srcFrames=raw.size()/srcCh;
    std::vector<float> stereo(srcFrames*2);
    for(size_t f=0;f<srcFrames;f++){
        float L=raw[f*srcCh];
        float R=(srcCh>1)?raw[f*srcCh+1]:L;
        stereo[f*2+0]=L; stereo[f*2+1]=R;
    }
    if(srcSr==SAMPLE_RATE){g_musicBuf=stereo;return;}
    double ratio=(double)SAMPLE_RATE/srcSr;
    size_t dstFrames=(size_t)(srcFrames*ratio);
    g_musicBuf.resize(dstFrames*2);
    for(size_t f=0;f<dstFrames;f++){
        double sf=f/ratio; size_t i0=(size_t)sf; double t=sf-i0;
        size_t i1=std::min(i0+1,srcFrames-1);
        g_musicBuf[f*2+0]=(float)(stereo[i0*2+0]*(1-t)+stereo[i1*2+0]*t);
        g_musicBuf[f*2+1]=(float)(stereo[i0*2+1]*(1-t)+stereo[i1*2+1]*t);
    }
}

static bool loadAudioFile(const std::string& path){
    // Reset drain state and SoundTouch buffer when loading a new track
    g_draining.store(false);
    g_mSt.flush(); g_mSt.clear();
    g_mStOutBuf.clear();
    std::lock_guard<std::mutex> lk(g_musicMtx);
    g_musicBuf.clear(); g_musicPos=0; g_musicLoaded=false;
    std::string ext=path.substr(path.find_last_of('.'));
    for(char& c:ext) c=(char)tolower(c);
    if(ext==".wav"||ext==".flac"){
        drwav wav;
        if(!drwav_init_file(&wav,path.c_str(),nullptr)) return false;
        size_t tf=(size_t)wav.totalPCMFrameCount;
        std::vector<float> raw(tf*wav.channels);
        drwav_read_pcm_frames_f32(&wav,tf,raw.data());
        int ch=wav.channels,sr=wav.sampleRate;
        drwav_uninit(&wav);
        resampleAndConvert(raw,ch,sr);
    } else if(ext==".mp3"){
        drmp3 mp3;
        if(!drmp3_init_file(&mp3,path.c_str(),nullptr)) return false;
        drmp3_uint64 tf=drmp3_get_pcm_frame_count(&mp3);
        std::vector<float> raw((size_t)tf*mp3.channels);
        drmp3_read_pcm_frames_f32(&mp3,(drmp3_uint64)tf,raw.data());
        int ch=mp3.channels,sr=mp3.sampleRate;
        drmp3_uninit(&mp3);
        resampleAndConvert(raw,ch,sr);
    } else if(ext==".m4a"||ext==".webm"||ext==".opus"||ext==".ogg"){
        // Use miniaudio's built-in decoder for these formats
        ma_decoder_config dcfg=ma_decoder_config_init(ma_format_f32,CHANNELS,SAMPLE_RATE);
        ma_decoder dec;
        if(ma_decoder_init_file(path.c_str(),&dcfg,&dec)!=MA_SUCCESS) return false;
        ma_uint64 totalFrames=0;
        ma_decoder_get_length_in_pcm_frames(&dec,&totalFrames);
        if(totalFrames==0) totalFrames=SAMPLE_RATE*600; // fallback: 10min max
        g_musicBuf.resize((size_t)totalFrames*CHANNELS);
        ma_uint64 framesRead=0;
        ma_decoder_read_pcm_frames(&dec,g_musicBuf.data(),totalFrames,&framesRead);
        g_musicBuf.resize((size_t)framesRead*CHANNELS);
        ma_decoder_uninit(&dec);
    } else return false;
    g_musicLoaded=true;
    return true;
}

static void scanMusicDir(const std::string& dir){
    g_musicList.clear();
    if(!std::filesystem::exists(dir)) return;
    for(auto& e:std::filesystem::directory_iterator(dir)){
        if(!e.is_regular_file()) continue;
        auto ext=e.path().extension().string();
        for(char& c:ext) c=(char)tolower(c);
        if(ext==".wav"||ext==".mp3"||ext==".flac"||ext==".m4a"||ext==".webm"||ext==".opus"||ext==".ogg"){
            g_musicList.push_back({e.path().filename().string(),e.path().string()});
        }
    }
    std::sort(g_musicList.begin(),g_musicList.end(),[](auto&a,auto&b){return a.name<b.name;});
}

static void enumerateDevices(){
    g_inputDevNames.clear(); g_outputDevNames.clear();
    ma_context_get_devices(&g_maCtx,&g_pPlaybackInfos,&g_playbackCount,
                           &g_pCaptureInfos,&g_captureCount);
    for(ma_uint32 i=0;i<g_captureCount;i++)  g_inputDevNames.push_back(g_pCaptureInfos[i].name);
    for(ma_uint32 i=0;i<g_playbackCount;i++) g_outputDevNames.push_back(g_pPlaybackInfos[i].name);
}

static int autoPickSpeakers(){
    for(int i=0;i<(int)g_outputDevNames.size();i++)
        if(g_outputDevNames[i].find("CABLE")==std::string::npos&&
           g_outputDevNames[i].find("VB-Audio")==std::string::npos)
            return i;
    return -1;
}

static bool openMonitorDevice(ma_device& dev, bool& devInit, int devIdx,
                               ma_device_data_proc callback, std::mutex& mtx, std::deque<float>& buf){
    if(devInit){ma_device_uninit(&dev);devInit=false;}
    {std::lock_guard<std::mutex> lk(mtx); buf.clear();}
    if(devIdx<0||(ma_uint32)devIdx>=g_playbackCount) return false;
    ma_device_config cfg=ma_device_config_init(ma_device_type_playback);
    cfg.playback.pDeviceID=&g_pPlaybackInfos[devIdx].id;
    cfg.playback.format=ma_format_f32;
    cfg.playback.channels=CHANNELS;
    cfg.sampleRate=SAMPLE_RATE;
    cfg.periodSizeInFrames=FRAME_SIZE;
    cfg.dataCallback=callback;
    cfg.pUserData=nullptr;
    if(ma_device_init(&g_maCtx,&cfg,&dev)!=MA_SUCCESS) return false;
    ma_device_start(&dev);
    devInit=true;
    return true;
}

static void startMonitorVoice(){
    int idx=g_settings.listenVoiceDeviceIndex;
    if(idx<0) idx=autoPickSpeakers();
    if(idx>=0) g_settings.listenVoiceDeviceIndex=idx;
    openMonitorDevice(g_monVoiceDev,g_monVoiceDevInit,idx,
        monitorVoiceCallback,g_monVoiceMtx,g_monVoiceBuf);
}
static void stopMonitorVoice(){
    if(g_monVoiceDevInit){ma_device_uninit(&g_monVoiceDev);g_monVoiceDevInit=false;}
    {std::lock_guard<std::mutex> lk(g_monVoiceMtx); g_monVoiceBuf.clear();}
}
static void startMonitorMusic(){
    int idx=g_settings.listenMusicDeviceIndex;
    if(idx<0) idx=autoPickSpeakers();
    if(idx>=0) g_settings.listenMusicDeviceIndex=idx;
    openMonitorDevice(g_monMusicDev,g_monMusicDevInit,idx,
        monitorMusicCallback,g_monMusicMtx,g_monMusicBuf);
}
static void stopMonitorMusic(){
    if(g_monMusicDevInit){ma_device_uninit(&g_monMusicDev);g_monMusicDevInit=false;}
    {std::lock_guard<std::mutex> lk(g_monMusicMtx); g_monMusicBuf.clear();}
}

// FIX #4: Start raw capture device for always-on monitor voice feed
static void startRawCapture(){
    if(g_rawCapDevInit){ma_device_uninit(&g_rawCapDev);g_rawCapDevInit=false;}
    int in=g_settings.inputDeviceIndex;
    if(in<0||(ma_uint32)in>=g_captureCount) return;
    ma_device_config cfg=ma_device_config_init(ma_device_type_capture);
    cfg.capture.pDeviceID=&g_pCaptureInfos[in].id;
    cfg.capture.format=ma_format_f32;
    cfg.capture.channels=1;
    cfg.sampleRate=SAMPLE_RATE;
    cfg.periodSizeInFrames=FRAME_SIZE;
    cfg.dataCallback=rawCaptureCallback;
    cfg.pUserData=nullptr;
    if(ma_device_init(&g_maCtx,&cfg,&g_rawCapDev)==MA_SUCCESS){
        ma_device_start(&g_rawCapDev);
        g_rawCapDevInit=true;
    }
}
static void stopRawCapture(){
    if(g_rawCapDevInit){ma_device_uninit(&g_rawCapDev);g_rawCapDevInit=false;}
}

static void stopDevices(){
    stopMonitorVoice();
    stopMonitorMusic();
    stopRawCapture();
    if(g_capDevInit){ma_device_uninit(&g_capDev);g_capDevInit=false;}
    if(g_outDevInit){ma_device_uninit(&g_outDev);g_outDevInit=false;}
    g_devicesStarted=false;
}

static bool startDevices(){
    stopDevices();
    int in=g_settings.inputDeviceIndex, out=g_settings.outputDeviceIndex;
    if(out<0||(ma_uint32)out>=g_playbackCount){
        snprintf(g_statusMsg,sizeof(g_statusMsg),"ERROR: No output device selected!");
        return false;
    }

    // Playback (virtual cable)
    {ma_device_config cfg=ma_device_config_init(ma_device_type_playback);
     cfg.playback.pDeviceID=&g_pPlaybackInfos[out].id;
     cfg.playback.format=ma_format_f32;
     cfg.playback.channels=CHANNELS;
     cfg.sampleRate=SAMPLE_RATE;
     cfg.periodSizeInFrames=FRAME_SIZE;
     cfg.dataCallback=playbackCallback;
     cfg.pUserData=nullptr;
     if(ma_device_init(&g_maCtx,&cfg,&g_outDev)!=MA_SUCCESS){
         snprintf(g_statusMsg,sizeof(g_statusMsg),"ERROR: Failed to open output device!");
         return false;
     }
     ma_device_start(&g_outDev);
     g_outDevInit=true;}

    // Capture (mic) - PTT-gated, feeds virtual mic
    if(in>=0&&(ma_uint32)in<g_captureCount){
        ma_device_config cfg=ma_device_config_init(ma_device_type_capture);
        cfg.capture.pDeviceID=&g_pCaptureInfos[in].id;
        cfg.capture.format=ma_format_f32;
        cfg.capture.channels=1;
        cfg.sampleRate=SAMPLE_RATE;
        cfg.periodSizeInFrames=FRAME_SIZE;
        cfg.dataCallback=captureCallback;
        cfg.pUserData=nullptr;
        if(ma_device_init(&g_maCtx,&cfg,&g_capDev)==MA_SUCCESS){
            ma_device_start(&g_capDev);
            g_capDevInit=true;
        }
    }

    // Monitor devices (always start if enabled, independent of PTT mode)
    if(g_settings.listenVoiceEnabled) startMonitorVoice();
    if(g_settings.listenMusicEnabled) startMonitorMusic();

    // FIX #4: Start raw capture for always-on monitor voice (if voice monitor enabled)
    if(g_settings.listenVoiceEnabled && in>=0) startRawCapture();

    g_devicesStarted=true;
    snprintf(g_statusMsg,sizeof(g_statusMsg),"Devices started! Audio routing active.");
    return true;
}

static void updateEffects(){
    g_st.setPitchSemiTones(g_settings.pitchEnabled?g_settings.pitchSemitones:0.0f);
    g_monSt.setPitchSemiTones(g_settings.pitchEnabled?g_settings.pitchSemitones:0.0f);
    g_reverb.setDecay(g_settings.reverbDecay);
    g_reverb.mix=g_settings.reverbMix;
    // Sync monitor reverb/echo to match mic settings
    g_monReverb.setDecay(g_settings.reverbDecay);
    g_monReverb.mix=g_settings.reverbMix;
    g_monEcho.feedback=g_settings.echoFeedback;
    g_monEcho.mix=g_settings.echoMix;
    g_monEcho.setDelay(g_settings.echoDelay);
    g_gate.threshold=g_settings.noiseGateThreshold;
    g_eqL.lowShelf(200.0f,g_settings.eqLow,SAMPLE_RATE);
    g_eqM.peaking(1000.0f,g_settings.eqMid,0.7f,SAMPLE_RATE);
    g_eqH.highShelf(5000.0f,g_settings.eqHigh,SAMPLE_RATE);
    g_echo.feedback=g_settings.echoFeedback;
    g_echo.mix=g_settings.echoMix;
    g_echo.setDelay(g_settings.echoDelay);
}
static void updateMusicEffects(){
    bool wasMStActive=g_mStActive;
    g_mStActive=(g_settings.mPitchEnabled && fabsf(g_settings.mPitchSemitones)>0.01f)
               ||(g_settings.mSpeedEnabled && fabsf(g_settings.mSpeedPercent-100.0f)>0.5f);
    g_mSt.setPitchSemiTones(g_settings.mPitchEnabled?g_settings.mPitchSemitones:0.0f);
    // setTempoChange takes percent relative to original: 0=normal, +50=50% faster, -50=half speed
    // User sees 50-150%, we convert: tempoChange = userPct - 100
    float tempoChange=g_settings.mSpeedEnabled?(g_settings.mSpeedPercent-100.0f):0.0f;
    g_mSt.setTempoChange(tempoChange);
    if(wasMStActive && !g_mStActive){
        // Turned off: flush remaining samples and clear queue
        g_mSt.flush(); g_mSt.clear();
        g_mStOutBuf.clear();
    }
    g_mReverb.setDecay(g_settings.mReverbDecay);
    g_mReverb.mix=g_settings.mReverbMix;
    g_mEqL.lowShelf(200.0f,g_settings.mEqLow,SAMPLE_RATE);
    g_mEqM.peaking(1000.0f,g_settings.mEqMid,0.7f,SAMPLE_RATE);
    g_mEqH.highShelf(5000.0f,g_settings.mEqHigh,SAMPLE_RATE);
    g_mEcho.feedback=g_settings.mEchoFeedback;
    g_mEcho.mix=g_settings.mEchoMix;
    g_mEcho.setDelay(g_settings.mEchoDelay);
}

static void saveSettings(const std::string& path){
    std::ofstream f(path);
    if(!f) return;
    f<<"{\n";
    f<<"  \"inputDeviceIndex\":"<<g_settings.inputDeviceIndex<<",\n";
    f<<"  \"outputDeviceIndex\":"<<g_settings.outputDeviceIndex<<",\n";
    f<<"  \"listenDeviceIndex\":"<<g_settings.listenDeviceIndex<<",\n";
    f<<"  \"listenEnabled\":"<<(g_settings.listenEnabled?"true":"false")<<",\n";
    f<<"  \"musicVolume\":"<<g_settings.musicVolume<<",\n";
    f<<"  \"micVolume\":"<<g_settings.micVolume<<",\n";
    f<<"  \"masterVolume\":"<<g_settings.masterVolume<<",\n";
    f<<"  \"micMode\":"<<g_settings.micMode<<",\n";
    f<<"  \"pitchEnabled\":"<<(g_settings.pitchEnabled?"true":"false")<<",\n";
    f<<"  \"pitchSemitones\":"<<g_settings.pitchSemitones<<",\n";
    f<<"  \"reverbEnabled\":"<<(g_settings.reverbEnabled?"true":"false")<<",\n";
    f<<"  \"reverbDecay\":"<<g_settings.reverbDecay<<",\n";
    f<<"  \"reverbMix\":"<<g_settings.reverbMix<<",\n";
    f<<"  \"robotEnabled\":"<<(g_settings.robotEnabled?"true":"false")<<",\n";
    f<<"  \"noiseGateEnabled\":"<<(g_settings.noiseGateEnabled?"true":"false")<<",\n";
    f<<"  \"noiseGateThreshold\":"<<g_settings.noiseGateThreshold<<",\n";
    f<<"  \"eqEnabled\":"<<(g_settings.eqEnabled?"true":"false")<<",\n";
    f<<"  \"eqLow\":"<<g_settings.eqLow<<",\n";
    f<<"  \"eqMid\":"<<g_settings.eqMid<<",\n";
    f<<"  \"eqHigh\":"<<g_settings.eqHigh<<",\n";
    f<<"  \"loopEnabled\":"<<(g_settings.loopEnabled?"true":"false")<<",\n";
    f<<"  \"listenVoiceEnabled\":"<<(g_settings.listenVoiceEnabled?"true":"false")<<",\n";
    f<<"  \"listenMusicEnabled\":"<<(g_settings.listenMusicEnabled?"true":"false")<<",\n";
    f<<"  \"listenVoiceDeviceIndex\":"<<g_settings.listenVoiceDeviceIndex<<",\n";
    f<<"  \"listenMusicDeviceIndex\":"<<g_settings.listenMusicDeviceIndex<<",\n";
    f<<"  \"echoEnabled\":"<<(g_settings.echoEnabled?"true":"false")<<",\n";
    f<<"  \"echoDelay\":"<<g_settings.echoDelay<<",\n";
    f<<"  \"echoFeedback\":"<<g_settings.echoFeedback<<",\n";
    f<<"  \"echoMix\":"<<g_settings.echoMix<<",\n";
    f<<"  \"effectsOnClips\":"<<(g_settings.effectsOnClips?"true":"false")<<",\n";
    f<<"  \"effectsOnMusic\":"<<(g_settings.effectsOnMusic?"true":"false")<<",\n";
    f<<"  \"stackableAudio\":"<<(g_settings.stackableAudio?"true":"false")<<",\n";
    f<<"  \"mPitchEnabled\":"<<(g_settings.mPitchEnabled?"true":"false")<<",\n";
    f<<"  \"mPitchSemitones\":"<<g_settings.mPitchSemitones<<",\n";
    f<<"  \"mReverbEnabled\":"<<(g_settings.mReverbEnabled?"true":"false")<<",\n";
    f<<"  \"mReverbDecay\":"<<g_settings.mReverbDecay<<",\n";
    f<<"  \"mReverbMix\":"<<g_settings.mReverbMix<<",\n";
    f<<"  \"mEchoEnabled\":"<<(g_settings.mEchoEnabled?"true":"false")<<",\n";
    f<<"  \"mEchoDelay\":"<<g_settings.mEchoDelay<<",\n";
    f<<"  \"mEchoFeedback\":"<<g_settings.mEchoFeedback<<",\n";
    f<<"  \"mEchoMix\":"<<g_settings.mEchoMix<<",\n";
    f<<"  \"mRobotEnabled\":"<<(g_settings.mRobotEnabled?"true":"false")<<",\n";
    f<<"  \"mEqEnabled\":"<<(g_settings.mEqEnabled?"true":"false")<<",\n";
    f<<"  \"mEqLow\":"<<g_settings.mEqLow<<",\n";
    f<<"  \"mEqMid\":"<<g_settings.mEqMid<<",\n";
    f<<"  \"mEqHigh\":"<<g_settings.mEqHigh<<",\n";
    f<<"  \"mSpeedEnabled\":"<<(g_settings.mSpeedEnabled?"true":"false")<<",\n";
    f<<"  \"mSpeedPercent\":"<<g_settings.mSpeedPercent<<",\n";
    f<<"  \"ttsVoiceIndex\":"<<g_settings.ttsVoiceIndex<<",\n";
    f<<"  \"ttsRate\":"<<g_settings.ttsRate<<",\n";
    f<<"  \"ttsVolume\":"<<g_settings.ttsVolume<<",\n";
    // Binds
    f<<"  \"binds\":{\n";
    bool first=true;
    for(auto& [k,v]:g_settings.binds){
        if(!first) f<<",\n";
        f<<"    \""<<k<<"\":\""<<v<<"\"";
        first=false;
    }
    f<<"\n  }\n";
    f<<"}\n";
}

static void loadSettings(const std::string& path){
    std::ifstream f(path);
    if(!f) return;
    std::string c((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    auto ri=[&](const std::string& k,int& v){
        auto p=c.find("\""+k+"\":");
        if(p==std::string::npos)return;
        p=c.find_first_of("-0123456789",p+k.size()+3);
        if(p!=std::string::npos)v=std::stoi(c.substr(p));
    };
    auto rf=[&](const std::string& k,float& v){
        auto p=c.find("\""+k+"\":");
        if(p==std::string::npos)return;
        p=c.find_first_of("-0123456789.",p+k.size()+3);
        if(p!=std::string::npos)v=std::stof(c.substr(p));
    };
    auto rb=[&](const std::string& k,bool& v){
        auto p=c.find("\""+k+"\":");
        if(p==std::string::npos)return;
        p+=k.size()+3;
        while(p<c.size()&&c[p]==' ')p++;
        v=(c.substr(p,4)=="true");
    };
    ri("inputDeviceIndex",g_settings.inputDeviceIndex);
    ri("outputDeviceIndex",g_settings.outputDeviceIndex);
    ri("listenDeviceIndex",g_settings.listenDeviceIndex);
    rb("listenEnabled",g_settings.listenEnabled);
    rf("musicVolume",g_settings.musicVolume);
    rf("micVolume",g_settings.micVolume);
    rf("masterVolume",g_settings.masterVolume);
    ri("micMode",g_settings.micMode);
    rb("pitchEnabled",g_settings.pitchEnabled);
    rf("pitchSemitones",g_settings.pitchSemitones);
    rb("reverbEnabled",g_settings.reverbEnabled);
    rf("reverbDecay",g_settings.reverbDecay);
    rf("reverbMix",g_settings.reverbMix);
    rb("robotEnabled",g_settings.robotEnabled);
    rb("noiseGateEnabled",g_settings.noiseGateEnabled);
    rf("noiseGateThreshold",g_settings.noiseGateThreshold);
    rb("eqEnabled",g_settings.eqEnabled);
    rf("eqLow",g_settings.eqLow);
    rf("eqMid",g_settings.eqMid);
    rf("eqHigh",g_settings.eqHigh);
    rb("loopEnabled",g_settings.loopEnabled);
    rb("listenVoiceEnabled",g_settings.listenVoiceEnabled);
    rb("listenMusicEnabled",g_settings.listenMusicEnabled);
    ri("listenVoiceDeviceIndex",g_settings.listenVoiceDeviceIndex);
    ri("listenMusicDeviceIndex",g_settings.listenMusicDeviceIndex);
    rb("echoEnabled",g_settings.echoEnabled);
    rf("echoDelay",g_settings.echoDelay);
    rf("echoFeedback",g_settings.echoFeedback);
    rf("echoMix",g_settings.echoMix);
    rb("effectsOnClips",g_settings.effectsOnClips);
    rb("effectsOnMusic",g_settings.effectsOnMusic);
    rb("stackableAudio",g_settings.stackableAudio);
    rb("mPitchEnabled",g_settings.mPitchEnabled);
    rf("mPitchSemitones",g_settings.mPitchSemitones);
    rb("mReverbEnabled",g_settings.mReverbEnabled);
    rf("mReverbDecay",g_settings.mReverbDecay);
    rf("mReverbMix",g_settings.mReverbMix);
    rb("mEchoEnabled",g_settings.mEchoEnabled);
    rf("mEchoDelay",g_settings.mEchoDelay);
    rf("mEchoFeedback",g_settings.mEchoFeedback);
    rf("mEchoMix",g_settings.mEchoMix);
    rb("mRobotEnabled",g_settings.mRobotEnabled);
    rb("mEqEnabled",g_settings.mEqEnabled);
    rf("mEqLow",g_settings.mEqLow);
    rf("mEqMid",g_settings.mEqMid);
    rf("mEqHigh",g_settings.mEqHigh);
    rb("mSpeedEnabled",g_settings.mSpeedEnabled);
    rf("mSpeedPercent",g_settings.mSpeedPercent);
    ri("ttsVoiceIndex",g_settings.ttsVoiceIndex);
    rf("ttsRate",g_settings.ttsRate);
    rf("ttsVolume",g_settings.ttsVolume);
    // Load binds
    auto bp=c.find("\"binds\":");
    if(bp!=std::string::npos){
        auto bo=c.find('{',bp);
        auto bc=c.find('}',bo);
        if(bo!=std::string::npos&&bc!=std::string::npos){
            std::string bindsStr=c.substr(bo+1,bc-bo-1);
            size_t pos=0;
            while(pos<bindsStr.size()){
                auto q1=bindsStr.find('"',pos);
                if(q1==std::string::npos) break;
                auto q2=bindsStr.find('"',q1+1);
                if(q2==std::string::npos) break;
                std::string keyStr=bindsStr.substr(q1+1,q2-q1-1);
                auto q3=bindsStr.find('"',q2+1);
                if(q3==std::string::npos) break;
                auto q4=bindsStr.find('"',q3+1);
                if(q4==std::string::npos) break;
                std::string val=bindsStr.substr(q3+1,q4-q3-1);
                try{ g_settings.binds[std::stoi(keyStr)]=val; }catch(...){}
                pos=q4+1;
            }
        }
    }
}

// ─── ImGui Custom Styles ──────────────────────────────────────────────────────
static void applyDarkTheme(){
    ImGuiStyle& s=ImGui::GetStyle();
    s.WindowRounding=8.0f; s.FrameRounding=4.0f; s.GrabRounding=4.0f;
    s.ScrollbarRounding=4.0f; s.TabRounding=4.0f;
    s.FramePadding={8,4}; s.ItemSpacing={8,6};
    s.WindowBorderSize=1.0f; s.FrameBorderSize=0.0f;
    ImVec4* c=s.Colors;
    c[ImGuiCol_WindowBg]         ={0.10f,0.10f,0.12f,1.0f};
    c[ImGuiCol_ChildBg]          ={0.13f,0.13f,0.16f,1.0f};
    c[ImGuiCol_PopupBg]          ={0.12f,0.12f,0.15f,0.97f};
    c[ImGuiCol_Border]           ={0.25f,0.25f,0.30f,0.6f};
    c[ImGuiCol_FrameBg]          ={0.18f,0.18f,0.22f,1.0f};
    c[ImGuiCol_FrameBgHovered]   ={0.22f,0.22f,0.28f,1.0f};
    c[ImGuiCol_FrameBgActive]    ={0.26f,0.26f,0.32f,1.0f};
    c[ImGuiCol_TitleBg]          ={0.08f,0.08f,0.10f,1.0f};
    c[ImGuiCol_TitleBgActive]    ={0.12f,0.12f,0.16f,1.0f};
    c[ImGuiCol_MenuBarBg]        ={0.12f,0.12f,0.15f,1.0f};
    c[ImGuiCol_ScrollbarBg]      ={0.10f,0.10f,0.12f,1.0f};
    c[ImGuiCol_ScrollbarGrab]    ={0.30f,0.30f,0.38f,1.0f};
    c[ImGuiCol_ScrollbarGrabHovered] ={0.40f,0.40f,0.50f,1.0f};
    c[ImGuiCol_ScrollbarGrabActive]  ={0.50f,0.50f,0.60f,1.0f};
    c[ImGuiCol_CheckMark]        ={0.26f,0.59f,0.98f,1.0f};
    c[ImGuiCol_SliderGrab]       ={0.26f,0.59f,0.98f,0.9f};
    c[ImGuiCol_SliderGrabActive] ={0.46f,0.79f,1.0f,1.0f};
    c[ImGuiCol_Button]           ={0.20f,0.40f,0.70f,0.8f};
    c[ImGuiCol_ButtonHovered]    ={0.26f,0.59f,0.98f,1.0f};
    c[ImGuiCol_ButtonActive]     ={0.06f,0.53f,0.98f,1.0f};
    c[ImGuiCol_Header]           ={0.20f,0.40f,0.70f,0.5f};
    c[ImGuiCol_HeaderHovered]    ={0.26f,0.59f,0.98f,0.8f};
    c[ImGuiCol_HeaderActive]     ={0.26f,0.59f,0.98f,1.0f};
    c[ImGuiCol_Tab]              ={0.15f,0.28f,0.50f,0.8f};
    c[ImGuiCol_TabHovered]       ={0.26f,0.59f,0.98f,0.8f};
    c[ImGuiCol_TabActive]        ={0.20f,0.41f,0.68f,1.0f};
    c[ImGuiCol_Text]             ={0.92f,0.92f,0.95f,1.0f};
    c[ImGuiCol_TextDisabled]     ={0.50f,0.50f,0.55f,1.0f};
    c[ImGuiCol_Separator]        ={0.25f,0.25f,0.30f,0.8f};
    c[ImGuiCol_PlotLines]        ={0.26f,0.59f,0.98f,1.0f};
    c[ImGuiCol_PlotHistogram]    ={0.26f,0.59f,0.98f,1.0f};
}

// ─── Notification helper ──────────────────────────────────────────────────────
static void showNotif(const char* msg, float dur=2.0f){
    g_notifText=msg; g_notifTimer=dur;
}

// ─── Main UI ─────────────────────────────────────────────────────────────────
static void renderUI(const std::string& appDir, const std::string& musicDir){
    ImGuiIO& io=ImGui::GetIO();
    ImGui::SetNextWindowPos({0,0});
    ImGui::SetNextWindowSize(io.DisplaySize);
    ImGui::Begin("##main",nullptr,
        ImGuiWindowFlags_NoTitleBar|ImGuiWindowFlags_NoResize|
        ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoScrollbar|
        ImGuiWindowFlags_MenuBar|ImGuiWindowFlags_NoBringToFrontOnFocus);

    // ── Menu Bar ─────────────────────────────────────────────────────────────
    if(ImGui::BeginMenuBar()){
        if(ImGui::BeginMenu("File")){
            if(ImGui::MenuItem("Open Music Folder")) ShellExecuteA(nullptr,"open",musicDir.c_str(),nullptr,nullptr,SW_SHOW);
            if(ImGui::MenuItem("Refresh Music List")) scanMusicDir(musicDir);
            ImGui::Separator();
            if(ImGui::MenuItem("Save Settings")) saveSettings(appDir+"\\settings.json");
            ImGui::Separator();
            if(ImGui::MenuItem("Exit")) PostQuitMessage(0);
            ImGui::EndMenu();
        }
        if(ImGui::BeginMenu("Binds")){
            ImGui::TextDisabled("Select a track first, then bind it to a key.");
            ImGui::Separator();
            for(int i=0;i<10;i++){
                std::string lbl="Ctrl+"+std::to_string(i)+": ";
                if(g_settings.binds.count(i)) lbl+=g_settings.binds[i];
                else lbl+="(none)";
                if(ImGui::MenuItem(lbl.c_str())){
                    if(g_selectedTrack>=0&&g_selectedTrack<(int)g_musicList.size()){
                        g_settings.binds[i]=g_musicList[g_selectedTrack].name;
                        g_bindTrack[i]=g_selectedTrack;
                        showNotif(("Bound Ctrl+"+std::to_string(i)+" to "+g_musicList[g_selectedTrack].name).c_str());
                    } else showNotif("Select a track first!");
                }
            }
            ImGui::EndMenu();
        }
        if(ImGui::BeginMenu("Help")){
            if(ImGui::MenuItem("Get VB-Cable (required)"))
                ShellExecuteA(nullptr,"open","https://vb-audio.com/Cable/",nullptr,nullptr,SW_SHOW);
            if(ImGui::MenuItem("GitHub Repository"))
                ShellExecuteA(nullptr,"open","https://github.com/dairyking98/Voice-Chat-DJ",nullptr,nullptr,SW_SHOW);
            ImGui::Separator();
            ImGui::MenuItem(("VoiceDJ v"+std::string(APP_VERSION)).c_str(),nullptr,false,false);
            ImGui::EndMenu();
        }
        ImGui::EndMenuBar();
    }

    float totalW=io.DisplaySize.x-16;
    // Clamp panel width to reasonable bounds
    g_leftPanelW=std::max(200.0f,std::min(g_leftPanelW,totalW-200.0f));
    float leftW=g_leftPanelW, rightW=totalW-leftW-8;

    // ── LEFT PANEL ────────────────────────────────────────────────────────────
    ImGui::BeginChild("##left",{leftW,0},true);

    // Device Selection
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  DEVICE SETUP");
    ImGui::Separator();

    // Input device
    {const char* preview=g_settings.inputDeviceIndex>=0&&g_settings.inputDeviceIndex<(int)g_inputDevNames.size()?
        g_inputDevNames[g_settings.inputDeviceIndex].c_str():"-- Select Microphone --";
     ImGui::Text("Microphone (Input):");
     ImGui::SetNextItemWidth(-1);
     if(ImGui::BeginCombo("##indev",preview)){
         for(int i=0;i<(int)g_inputDevNames.size();i++){
             bool sel=(i==g_settings.inputDeviceIndex);
             if(ImGui::Selectable(g_inputDevNames[i].c_str(),sel))
                 g_settings.inputDeviceIndex=i;
             if(sel) ImGui::SetItemDefaultFocus();
         }
         ImGui::EndCombo();
     }}

    // Output device
    {const char* preview=g_settings.outputDeviceIndex>=0&&g_settings.outputDeviceIndex<(int)g_outputDevNames.size()?
        g_outputDevNames[g_settings.outputDeviceIndex].c_str():"-- Select Virtual Cable --";
     ImGui::Text("Virtual Cable (Output):");
     ImGui::SetNextItemWidth(-1);
     if(ImGui::BeginCombo("##outdev",preview)){
         for(int i=0;i<(int)g_outputDevNames.size();i++){
             bool sel=(i==g_settings.outputDeviceIndex);
             bool isVB=g_outputDevNames[i].find("VB-Audio")!=std::string::npos||
                        g_outputDevNames[i].find("CABLE")!=std::string::npos;
             if(isVB) ImGui::PushStyleColor(ImGuiCol_Text,{0.4f,1.0f,0.4f,1.0f});
             if(ImGui::Selectable(g_outputDevNames[i].c_str(),sel))
                 g_settings.outputDeviceIndex=i;
             if(isVB) ImGui::PopStyleColor();
             if(sel) ImGui::SetItemDefaultFocus();
         }
         ImGui::EndCombo();
     }}

    // FIX #3: Separate Monitor Voice and Monitor Music checkboxes
    // ── Monitor Voice (hear your own mic in headphones) ──────────────────────
    {
        bool prev=g_settings.listenVoiceEnabled;
        ImGui::Checkbox("Monitor Voice (hear mic)",&g_settings.listenVoiceEnabled);
        if(g_settings.listenVoiceEnabled!=prev && g_devicesStarted){
            if(g_settings.listenVoiceEnabled){
                startMonitorVoice();
                startRawCapture(); // FIX #4: always-on raw capture for monitor
            } else {
                stopMonitorVoice();
                stopRawCapture();
            }
        }
        if(g_settings.listenVoiceEnabled){
            // FIX #4: Clarify that monitor is always-on
            ImGui::TextDisabled("  Always-on. PTT only gates virtual mic, not monitor.");
            const char* preview=g_settings.listenVoiceDeviceIndex>=0&&
                g_settings.listenVoiceDeviceIndex<(int)g_outputDevNames.size()?
                g_outputDevNames[g_settings.listenVoiceDeviceIndex].c_str():"-- Select Speakers --";
            ImGui::SetNextItemWidth(-1);
            if(ImGui::BeginCombo("##monvoicedev",preview)){
                for(int i=0;i<(int)g_outputDevNames.size();i++){
                    bool sel=(i==g_settings.listenVoiceDeviceIndex);
                    if(ImGui::Selectable(g_outputDevNames[i].c_str(),sel)){
                        g_settings.listenVoiceDeviceIndex=i;
                        if(g_devicesStarted){ startMonitorVoice(); startRawCapture(); }
                    }
                    if(sel) ImGui::SetItemDefaultFocus();
                }
                ImGui::EndCombo();
            }
        }
    }
    // ── Monitor Music (hear music/output in headphones) ───────────────────────
    {
        bool prev=g_settings.listenMusicEnabled;
        ImGui::Checkbox("Monitor Music (hear output)",&g_settings.listenMusicEnabled);
        if(g_settings.listenMusicEnabled!=prev && g_devicesStarted){
            if(g_settings.listenMusicEnabled) startMonitorMusic();
            else stopMonitorMusic();
        }
        if(g_settings.listenMusicEnabled){
            const char* preview=g_settings.listenMusicDeviceIndex>=0&&
                g_settings.listenMusicDeviceIndex<(int)g_outputDevNames.size()?
                g_outputDevNames[g_settings.listenMusicDeviceIndex].c_str():"-- Select Speakers --";
            ImGui::SetNextItemWidth(-1);
            if(ImGui::BeginCombo("##monmusicdev",preview)){
                for(int i=0;i<(int)g_outputDevNames.size();i++){
                    bool sel=(i==g_settings.listenMusicDeviceIndex);
                    if(ImGui::Selectable(g_outputDevNames[i].c_str(),sel)){
                        g_settings.listenMusicDeviceIndex=i;
                        if(g_devicesStarted) startMonitorMusic();
                    }
                    if(sel) ImGui::SetItemDefaultFocus();
                }
                ImGui::EndCombo();
            }
        }
    }

    ImGui::Spacing();
    // Start/Stop button
    if(!g_devicesStarted){
        ImGui::PushStyleColor(ImGuiCol_Button,{0.1f,0.6f,0.1f,1.0f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.2f,0.8f,0.2f,1.0f});
        if(ImGui::Button("  START AUDIO  ",{-1,36})) startDevices();
        ImGui::PopStyleColor(2);
    } else {
        ImGui::PushStyleColor(ImGuiCol_Button,{0.6f,0.1f,0.1f,1.0f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.8f,0.2f,0.2f,1.0f});
        if(ImGui::Button("  STOP AUDIO  ",{-1,36})) stopDevices();
        ImGui::PopStyleColor(2);
    }

    ImGui::Spacing(); ImGui::Separator(); ImGui::Spacing();

    // ── Volume Controls ───────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  VOLUME");
    ImGui::Separator();
    ImGui::Text("Master"); ImGui::SameLine(80);
    ImGui::SetNextItemWidth(-1);
    ImGui::SliderFloat("##master",&g_settings.masterVolume,0.0f,2.0f,"%.2f");
    ImGui::Text("Music");  ImGui::SameLine(80);
    ImGui::SetNextItemWidth(-1);
    ImGui::SliderFloat("##music",&g_settings.musicVolume,0.0f,3.0f,"%.2f");
    ImGui::Text("Mic");    ImGui::SameLine(80);
    ImGui::SetNextItemWidth(-1);
    ImGui::SliderFloat("##mic",&g_settings.micVolume,0.0f,2.0f,"%.2f");

    ImGui::Spacing(); ImGui::Separator(); ImGui::Spacing();

    // ── Mic Mode ─────────────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  MICROPHONE MODE");
    ImGui::Separator();
    const char* modes[]={"Off","Always On","Push-to-Talk (Mouse4)"};
    ImGui::SetNextItemWidth(-1);
    ImGui::Combo("##micmode",&g_settings.micMode,modes,3);
    if(g_settings.micMode==2){
        ImGui::TextDisabled("Hold Mouse4 (side button) to talk");
        bool ptt=g_pttActive;
        if(ptt) ImGui::TextColored({0.2f,1.0f,0.2f,1.0f},"  [MIC ACTIVE]");
        else ImGui::TextColored({0.5f,0.5f,0.5f,1.0f},"  [MIC INACTIVE]");
    }

    ImGui::Spacing(); ImGui::Separator(); ImGui::Spacing();

    // ── TTS ──────────────────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  TEXT-TO-SPEECH");
    ImGui::Separator();
    ImGui::TextDisabled("Ctrl+Tab to open TTS popup");
    if(ImGui::Button("Open TTS",{-1,0})){
        memset(g_ttsText,0,sizeof(g_ttsText));
        g_showTTSPopup=true;
        g_ttsJustOpened=true;
    }

    ImGui::EndChild(); // left panel
    ImGui::SameLine();
    // ── PANEL SPLITTER ────────────────────────────────────────────────────────
    {
        float splitterW=6.0f;
        ImVec2 splitterPos=ImGui::GetCursorScreenPos();
        float splitterH=io.DisplaySize.y-splitterPos.y-30;
        ImGui::InvisibleButton("##splitter",{splitterW,splitterH});
        if(ImGui::IsItemHovered())
            ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeEW);
        if(ImGui::IsItemActive()){
            g_leftPanelW+=io.MouseDelta.x;
            g_leftPanelW=std::max(200.0f,std::min(g_leftPanelW,totalW-200.0f));
        }
        // Draw a subtle divider line
        ImDrawList* dl=ImGui::GetWindowDrawList();
        ImU32 col=ImGui::IsItemHovered()||ImGui::IsItemActive()?
            IM_COL32(100,180,255,200):IM_COL32(80,80,80,120);
        dl->AddLine({splitterPos.x+splitterW/2,splitterPos.y},
                    {splitterPos.x+splitterW/2,splitterPos.y+splitterH},col,1.5f);
    }
    ImGui::SameLine();
    // ── RIGHT PANEL ───────────────────────────────────────────────────────────
    ImGui::BeginChild("##right",{rightW-6,0},false);

    // ── Spectrum Visualizer ───────────────────────────────────────────────────
    {
        ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  SPECTRUM ANALYZER");
        ImGui::Separator();
        updateSpectrum();
        ImVec2 canvasPos=ImGui::GetCursorScreenPos();
        float canvasW=rightW-16, canvasH=80;
        ImDrawList* dl=ImGui::GetWindowDrawList();
        dl->AddRectFilled(canvasPos,ImVec2{canvasPos.x+canvasW,canvasPos.y+canvasH},IM_COL32(0,0,0,200));
        // Draw bars
        int numBars=128;
        float barW=canvasW/numBars;
        for(int i=0;i<numBars;i++){
            int bin=(int)(i*(float)SPEC_BINS/numBars);
            float h=g_specData[bin]*canvasH;
            float hue=0.6f-(float)i/numBars*0.4f; // blue to cyan
            ImVec4 colv={hue*0.5f+0.2f,0.6f+hue*0.4f,1.0f,0.9f};
            ImU32 col=ImGui::ColorConvertFloat4ToU32(colv);
            dl->AddRectFilled(
                ImVec2{canvasPos.x+i*barW, canvasPos.y+canvasH-h},
                ImVec2{canvasPos.x+(i+1)*barW-1, canvasPos.y+canvasH},
                col);
        }
        ImGui::Dummy(ImVec2{canvasW,canvasH});
        ImGui::Spacing();
    }
    // ── Mic Effects Chain ────────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  MIC EFFECTS");
    ImGui::Separator();
    g_effPanelH=std::max(80.0f,std::min(g_effPanelH,io.DisplaySize.y-200.0f));
    ImGui::BeginChild("##eff",{0,g_effPanelH},true);

    // Pitch Shift
    ImGui::Checkbox("##pitch",&g_settings.pitchEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.pitchEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Pitch Shift");
    if(g_settings.pitchEnabled){
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##pitchst",&g_settings.pitchSemitones,-12.0f,12.0f,"%.1f st"))
            updateEffects();
        ImGui::TextDisabled("  -12 (deep) to +12 (chipmunk)");
    }
    ImGui::Spacing();

    // Reverb (own row)
    ImGui::Checkbox("##reverb",&g_settings.reverbEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.reverbEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Reverb");
    if(g_settings.reverbEnabled){
        ImGui::Text("Decay"); ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##rdecay",&g_settings.reverbDecay,0.1f,0.95f,"%.2f"))
            updateEffects();
        ImGui::Text("Mix");   ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##rmix",&g_settings.reverbMix,0.0f,1.0f,"%.2f"))
            updateEffects();
    }
    ImGui::Spacing();
    // Echo (own row)
    ImGui::Checkbox("##echo",&g_settings.echoEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.echoEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Echo");
    if(g_settings.echoEnabled){
        ImGui::Text("Delay");    ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##echodelay",&g_settings.echoDelay,0.05f,2.0f,"%.2f s"))
            updateEffects();
        ImGui::Text("Feedback"); ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##echofb",&g_settings.echoFeedback,0.0f,0.95f,"%.2f"))
            updateEffects();
        ImGui::Text("Mix");      ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##echomix",&g_settings.echoMix,0.0f,1.0f,"%.2f"))
            updateEffects();
        ImGui::TextDisabled("  High delay+feedback = echo...echo...echo...");
    }
    ImGui::Spacing();

    // Robot
    ImGui::Checkbox("##robot",&g_settings.robotEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.robotEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Robot Voice");
    ImGui::Spacing();

    // Noise Gate
    ImGui::Checkbox("##ngate",&g_settings.noiseGateEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.noiseGateEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Noise Gate");
    if(g_settings.noiseGateEnabled){
        ImGui::Text("Threshold"); ImGui::SameLine(90);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##ngth",&g_settings.noiseGateThreshold,0.001f,0.2f,"%.3f"))
            updateEffects();
    }
    ImGui::Spacing();

    ImGui::Spacing();

    // EQ
    ImGui::Checkbox("##eq",&g_settings.eqEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.eqEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"3-Band EQ");
    if(g_settings.eqEnabled){
        ImGui::Text("Low");  ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##eql",&g_settings.eqLow,-12.0f,12.0f,"%.1f dB")) updateEffects();
        ImGui::Text("Mid");  ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##eqm",&g_settings.eqMid,-12.0f,12.0f,"%.1f dB")) updateEffects();
        ImGui::Text("High"); ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##eqh",&g_settings.eqHigh,-12.0f,12.0f,"%.1f dB")) updateEffects();
    }
    ImGui::EndChild(); // mic effects
    // Vertical drag handle to resize mic effects panel
    {
        float splitterH=6.0f;
        ImVec2 sp=ImGui::GetCursorScreenPos();
        float spW=rightW-16;
        ImGui::InvisibleButton("##effSplit",{spW,splitterH});
        if(ImGui::IsItemHovered()) ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeNS);
        if(ImGui::IsItemActive()) g_effPanelH=std::max(80.0f,g_effPanelH+io.MouseDelta.y);
        ImDrawList* dl2=ImGui::GetWindowDrawList();
        ImU32 sc=ImGui::IsItemHovered()||ImGui::IsItemActive()?
            IM_COL32(100,180,255,200):IM_COL32(80,80,80,120);
        dl2->AddLine({sp.x,sp.y+splitterH/2},{sp.x+spW,sp.y+splitterH/2},sc,1.5f);
    }
    ImGui::Spacing();

    // ── Music Effects ───────────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  MUSIC EFFECTS");
    ImGui::Separator();
    g_meffPanelH=std::max(80.0f,std::min(g_meffPanelH,io.DisplaySize.y-200.0f));
    ImGui::BeginChild("##meff",{0,g_meffPanelH},true);

    // Effects on Hotkey Sounds
    ImGui::Checkbox("##fxclips",&g_settings.effectsOnClips); ImGui::SameLine();
    ImGui::TextColored(g_settings.effectsOnClips?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Effects on Hotkey Sounds");
    if(g_settings.effectsOnClips) ImGui::TextDisabled("  Hotkey clips play through music effects chain");
    ImGui::Spacing();
    // Effects on Music
    ImGui::Checkbox("##fxmusic",&g_settings.effectsOnMusic); ImGui::SameLine();
    ImGui::TextColored(g_settings.effectsOnMusic?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Effects on Music");
    if(g_settings.effectsOnMusic) ImGui::TextDisabled("  Playlist music plays through music effects chain");
    ImGui::Spacing();
    // Stackable Audio
    ImGui::Checkbox("##stackable",&g_settings.stackableAudio); ImGui::SameLine();
    ImGui::TextColored(g_settings.stackableAudio?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Stackable Hotkey Audio");
    if(g_settings.stackableAudio) ImGui::TextDisabled("  Spam clips - all play simultaneously");
    else ImGui::TextDisabled("  Single mode - new clip replaces current");
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextDisabled("Music Effects Chain:");
    ImGui::Spacing();
    // Music Pitch Shift
    ImGui::Checkbox("##mpitch",&g_settings.mPitchEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mPitchEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Pitch Shift");
    if(g_settings.mPitchEnabled){
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mpitchst",&g_settings.mPitchSemitones,-12.0f,12.0f,"%.1f st"))
            updateMusicEffects();
        ImGui::TextDisabled("  -12 (deep) to +12 (chipmunk)");
    }
    ImGui::Spacing();
    // Music Speed
    ImGui::Checkbox("##mspeed",&g_settings.mSpeedEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mSpeedEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Speed");
    if(g_settings.mSpeedEnabled){
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mspeedpct",&g_settings.mSpeedPercent,50.0f,150.0f,"%.0f%%"))
            updateMusicEffects();
        ImGui::TextDisabled("  50%% = half speed  |  100%% = normal  |  150%% = 1.5x speed");
    }
    ImGui::Spacing();
    // Music Reverb
    ImGui::Checkbox("##mreverb",&g_settings.mReverbEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mReverbEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Reverb");
    if(g_settings.mReverbEnabled){
        ImGui::Text("Decay"); ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mrdecay",&g_settings.mReverbDecay,0.1f,0.95f,"%.2f")) updateMusicEffects();
        ImGui::Text("Mix");   ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mrmix",&g_settings.mReverbMix,0.0f,1.0f,"%.2f")) updateMusicEffects();
    }
    ImGui::Spacing();
    // Music Echo
    ImGui::Checkbox("##mecho",&g_settings.mEchoEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mEchoEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Echo");
    if(g_settings.mEchoEnabled){
        ImGui::Text("Delay");    ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mechodelay",&g_settings.mEchoDelay,0.05f,2.0f,"%.2f s")) updateMusicEffects();
        ImGui::Text("Feedback"); ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mechofb",&g_settings.mEchoFeedback,0.0f,0.95f,"%.2f")) updateMusicEffects();
        ImGui::Text("Mix");      ImGui::SameLine(80);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##mechomix",&g_settings.mEchoMix,0.0f,1.0f,"%.2f")) updateMusicEffects();
    }
    ImGui::Spacing();
    // Music Robot
    ImGui::Checkbox("##mrobot",&g_settings.mRobotEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mRobotEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"Robot Voice");
    ImGui::Spacing();
    // Music 3-Band EQ
    ImGui::Checkbox("##meq",&g_settings.mEqEnabled); ImGui::SameLine();
    ImGui::TextColored(g_settings.mEqEnabled?ImVec4{0.4f,1.0f,0.4f,1.0f}:ImVec4{0.6f,0.6f,0.6f,1.0f},"3-Band EQ");
    if(g_settings.mEqEnabled){
        ImGui::Text("Low");  ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##meql",&g_settings.mEqLow,-12.0f,12.0f,"%.1f dB")) updateMusicEffects();
        ImGui::Text("Mid");  ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##meqm",&g_settings.mEqMid,-12.0f,12.0f,"%.1f dB")) updateMusicEffects();
        ImGui::Text("High"); ImGui::SameLine(50);
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##meqh",&g_settings.mEqHigh,-12.0f,12.0f,"%.1f dB")) updateMusicEffects();
    }

    ImGui::EndChild(); // music effects
    // Vertical drag handle to resize music effects panel
    {
        float splitterH=6.0f;
        ImVec2 sp=ImGui::GetCursorScreenPos();
        float spW=rightW-16;
        ImGui::InvisibleButton("##meffSplit",{spW,splitterH});
        if(ImGui::IsItemHovered()) ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeNS);
        if(ImGui::IsItemActive()) g_meffPanelH=std::max(80.0f,g_meffPanelH+io.MouseDelta.y);
        ImDrawList* dl3=ImGui::GetWindowDrawList();
        ImU32 sc2=ImGui::IsItemHovered()||ImGui::IsItemActive()?
            IM_COL32(100,180,255,200):IM_COL32(80,80,80,120);
        dl3->AddLine({sp.x,sp.y+splitterH/2},{sp.x+spW,sp.y+splitterH/2},sc2,1.5f);
    }
    ImGui::Spacing();

    // ── Music Playlist ───────────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  MUSIC PLAYLIST");
    ImGui::Separator();

    // ── YouTube Download ──────────────────────────────────────────────────────
    ImGui::TextColored({0.4f,0.8f,1.0f,1.0f},"  YOUTUBE DOWNLOAD");
    ImGui::Separator();
    ImGui::SetNextItemWidth(-120);
    ImGui::InputText("##yturl",g_ytUrl,sizeof(g_ytUrl),
        g_ytDownloading?ImGuiInputTextFlags_ReadOnly:0);
    ImGui::SameLine();
    if(g_ytDownloading){
        ImGui::PushStyleColor(ImGuiCol_Button,{0.4f,0.4f,0.1f,1.0f});
        ImGui::Button("Downloading...",{-1,0});
        ImGui::PopStyleColor();
    } else {
        ImGui::PushStyleColor(ImGuiCol_Button,{0.1f,0.5f,0.1f,1.0f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.2f,0.7f,0.2f,1.0f});
        if(ImGui::Button("Download",{-1,0})){
            std::string url=g_ytUrl;
            if(!url.empty()&&!g_ytDownloading){
                g_ytDownloading=true;
                g_ytStatus="Downloading...";
                if(g_ytThread.joinable()) g_ytThread.join();
                g_ytThread=std::thread([url](){
                    // Build path to yt-dlp.exe next to our EXE
                    char exePath[MAX_PATH]={};
                    GetModuleFileNameA(nullptr,exePath,MAX_PATH);
                    std::string appDir=std::string(exePath);
                    appDir=appDir.substr(0,appDir.find_last_of("\\/"));
                    std::string ytdlp=appDir+"\\yt-dlp.exe";
                    std::string ffmpeg=appDir+"\\ffmpeg.exe";
                    std::string outDir=g_musicDirGlobal;
                    bool hasFfmpeg=GetFileAttributesA(ffmpeg.c_str())!=INVALID_FILE_ATTRIBUTES;
                    std::string cmd;
                    if(hasFfmpeg){
                        // ffmpeg available: convert to MP3 for best compatibility
                        cmd="\""+ytdlp+"\" --no-playlist"
                            " --no-check-certificates"
                            " --ffmpeg-location \""+ffmpeg+"\""
                            " -x --audio-format mp3 --audio-quality 0"
                            " -o \""+outDir+"\\\\%(title)s.%(ext)s\""
                            " \""+url+"\"";
                    } else {
                        // No ffmpeg: prefer MP3/OGG native streams, fall back to best available
                        cmd="\""+ytdlp+"\" --no-playlist"
                            " --no-check-certificates"
                            " -f \"bestaudio[ext=mp3]/bestaudio[ext=ogg]/bestaudio[ext=m4a]/bestaudio\""
                            " -o \""+outDir+"\\\\%(title)s.%(ext)s\""
                            " \""+url+"\"";
                    }
                    STARTUPINFOA si={sizeof(si)};
                    PROCESS_INFORMATION pi;
                    si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_HIDE;
                    BOOL ok=CreateProcessA(nullptr,(LPSTR)cmd.c_str(),nullptr,nullptr,
                        FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&si,&pi);
                    if(ok){
                        WaitForSingleObject(pi.hProcess,120000); // 2min timeout
                        DWORD exitCode=1;
                        GetExitCodeProcess(pi.hProcess,&exitCode);
                        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
                        g_ytStatus=(exitCode==0)?"Download complete!":"Download failed (check URL)";
                    } else {
                        g_ytStatus="yt-dlp.exe not found next to VoiceDJ.exe";
                    }
                    // Refresh playlist
                    scanMusicDir(g_musicDirGlobal);
                    g_ytDownloading=false;
                });
            }
        }
        ImGui::PopStyleColor(2);
    }
    if(!g_ytStatus.empty()){
        bool ok=(g_ytStatus.find("complete")!=std::string::npos);
        ImGui::TextColored(ok?ImVec4{0.2f,1.0f,0.2f,1.0f}:ImVec4{1.0f,0.6f,0.2f,1.0f},
            "%s",g_ytStatus.c_str());
    }
    // ffmpeg hint
    {
        char exeP[MAX_PATH]={};
        GetModuleFileNameA(nullptr,exeP,MAX_PATH);
        std::string aDir=std::string(exeP); aDir=aDir.substr(0,aDir.find_last_of("\\/"));
        bool hasFfmpeg=GetFileAttributesA((aDir+"\\ffmpeg.exe").c_str())!=INVALID_FILE_ATTRIBUTES;
        if(!hasFfmpeg){
            ImGui::TextColored({1.0f,0.8f,0.2f,1.0f},"  Tip: Place ffmpeg.exe next to VoiceDJ.exe for MP3 conversion.");
            ImGui::SameLine();
            if(ImGui::SmallButton("Get ffmpeg"))
                ShellExecuteA(nullptr,"open",
                    "https://github.com/BtbN/FFmpeg-Builds/releases/latest",
                    nullptr,nullptr,SW_SHOW);
        } else {
            ImGui::TextColored({0.2f,1.0f,0.2f,1.0f},"  ffmpeg detected - downloads will be converted to MP3");
        }
    }
    ImGui::Spacing();

    // Playback controls
    {
        bool playing=(g_playState.load()==PlayState::Playing);
        bool paused =(g_playState.load()==PlayState::Paused);

        if(ImGui::Button(playing?"  Pause  ":"  Play  ")){
            if(playing) g_playState.store(PlayState::Paused);
            else if(paused) g_playState.store(PlayState::Playing);
            else if(g_selectedTrack>=0&&g_selectedTrack<(int)g_musicList.size()){
                if(loadAudioFile(g_musicList[g_selectedTrack].path)){
                    g_isClipPlaying.store(false); // playlist play, not a clip
                    g_playState.store(PlayState::Playing);
                    showNotif(("Playing: "+g_musicList[g_selectedTrack].name).c_str());
                }
            }
        }
        ImGui::SameLine();
        if(ImGui::Button("  Stop  ")){
            g_playState.store(PlayState::Stopped);
            g_isClipPlaying.store(false);
            std::lock_guard<std::mutex> lk(g_musicMtx);
            g_musicPos=0;
        }
        ImGui::SameLine();
        ImGui::Checkbox("Loop",&g_settings.loopEnabled);
        ImGui::SameLine();
        if(ImGui::Button("Refresh")) scanMusicDir(musicDir);
        ImGui::SameLine();
        if(ImGui::Button("Open Folder")) ShellExecuteA(nullptr,"open",musicDir.c_str(),nullptr,nullptr,SW_SHOW);

        // Progress bar
        float prog=0.0f;
        {std::lock_guard<std::mutex> lk(g_musicMtx);
         if(g_musicLoaded&&!g_musicBuf.empty())
             prog=(float)g_musicPos/g_musicBuf.size();}
        ImGui::SetNextItemWidth(-1);
        if(ImGui::SliderFloat("##prog",&prog,0.0f,1.0f,"",ImGuiSliderFlags_NoInput)){
            std::lock_guard<std::mutex> lk(g_musicMtx);
            if(g_musicLoaded) g_musicPos=(size_t)(prog*g_musicBuf.size());
        }
    }

    // Track list
    float listH=io.DisplaySize.y-ImGui::GetCursorPosY()-80;
    ImGui::BeginChild("##tracklist",{0,listH},true);
    for(int i=0;i<(int)g_musicList.size();i++){
        bool sel=(i==g_selectedTrack);
        bool playing=(i==g_selectedTrack&&g_playState.load()==PlayState::Playing);
        std::string label=(playing?"  > ":"    ")+g_musicList[i].name;

        // Check if bound
        for(auto& [k,v]:g_settings.binds){
            if(v==g_musicList[i].name){
                label="["+std::to_string(k)+"] "+label;
                break;
            }
        }

        if(ImGui::Selectable(label.c_str(),sel,ImGuiSelectableFlags_AllowDoubleClick)){
            g_selectedTrack=i;
            if(ImGui::IsMouseDoubleClicked(0)){
                if(loadAudioFile(g_musicList[i].path)){
                    g_isClipPlaying.store(false); // playlist play, not a clip
                    g_playState.store(PlayState::Playing);
                    showNotif(("Playing: "+g_musicList[i].name).c_str());
                }
            }
        }
    }
    if(g_musicList.empty()){
        ImGui::TextDisabled("No audio files found.");
        ImGui::TextDisabled("Add WAV/MP3 files to the 'music' folder.");
    }
    ImGui::EndChild();

    ImGui::EndChild(); // right panel

    // ── Status Bar ────────────────────────────────────────────────────────────
    ImGui::SetCursorPos({8, io.DisplaySize.y-30});
    ImGui::Separator();
    ImGui::SetCursorPos({8, io.DisplaySize.y-22});
    bool ok=g_devicesStarted;
    ImGui::TextColored(ok?ImVec4{0.2f,1.0f,0.2f,1.0f}:ImVec4{1.0f,0.6f,0.1f,1.0f},"%s",g_statusMsg);

    ImGui::End(); // main window

    // ── TTS background thread result handler ─────────────────────────────────
    // FIX #1: Handle TTS completion - play and/or save without closing the popup
    if(g_ttsState.load()==TTSState::Done){
        g_ttsState.store(TTSState::Idle);
        if(g_ttsThread.joinable()) g_ttsThread.join();

        bool doPlay  = !g_ttsSaveToLib || g_ttsSaveAndPlay;
        bool doSave  = g_ttsSaveToLib  || g_ttsSaveAndPlay;

        if(doSave){
            // Save to music library using the TTS text as filename
            // If a file with that name already exists, append a counter
            std::string baseName=g_ttsSaveFilename.empty()?"tts":g_ttsSaveFilename;
            std::string dest=g_musicDirGlobal+"\\"+baseName+".wav";
            int counter=1;
            while(GetFileAttributesA(dest.c_str())!=INVALID_FILE_ATTRIBUTES){
                dest=g_musicDirGlobal+"\\"+baseName+"_"+std::to_string(counter++)+".wav";
            }
            std::string savedName=dest.substr(dest.find_last_of("\\/")+1);
            CopyFileA(g_ttsPendingWav.c_str(),dest.c_str(),FALSE);
            scanMusicDir(g_musicDirGlobal);
            if(!doPlay) showNotif((std::string("Saved: ")+savedName).c_str());
        }
        if(doPlay){
            // Play through virtual mic
            if(loadAudioFile(g_ttsPendingWav)){
                g_isClipPlaying.store(false);
                g_playState.store(PlayState::Playing);
                if(doSave){
                    std::string savedName=g_ttsSaveFilename.empty()?"tts":g_ttsSaveFilename;
                    showNotif((std::string("TTS playing & saved as: ")+savedName+".wav").c_str());
                } else       showNotif("TTS playing through virtual mic...");
            }
        }
    } else if(g_ttsState.load()==TTSState::Error){
        g_ttsState.store(TTSState::Idle);
        if(g_ttsThread.joinable()) g_ttsThread.join();
        showNotif("TTS render failed — check PowerShell is available");
    }

    // ── TTS Popup ─────────────────────────────────────────────────────────────
    // FIX #1: TTS popup is a persistent window. It stays open after use.
    // Buttons are disabled while rendering. Close button works at all times.
    // FIX #1 (Ctrl+Tab): The hotkey only brings the TTS window to front if
    // it's already open, and only opens it if it's closed. It does NOT bring
    // the main window to front (which caused both windows to appear).
    if(g_showTTSPopup){
        // g_ttsJustOpened: set keyboard focus on first frame; bring-to-front is done in WM_HOTKEY
        bool doFocus=g_ttsJustOpened;
        if(g_ttsJustOpened) g_ttsJustOpened=false;

        ImGui::SetNextWindowSize({440,170},ImGuiCond_Always);
        ImGui::SetNextWindowPos({io.DisplaySize.x/2-220,io.DisplaySize.y/2-85},ImGuiCond_Always);
        bool popupOpen=true;
        ImGui::Begin("Text-to-Speech  [Ctrl+Tab]",&popupOpen,
            ImGuiWindowFlags_NoResize|ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoCollapse);
        if(!popupOpen){
            g_showTTSPopup=false;
            ImGui::End();
            goto tts_end;
        }
        ImGui::Text("Type text to speak through virtual mic:");
        ImGui::SetNextItemWidth(-1);
        if(doFocus) ImGui::SetKeyboardFocusHere(0);
        bool enter=ImGui::InputText("##ttstext",g_ttsText,sizeof(g_ttsText),
            ImGuiInputTextFlags_EnterReturnsTrue);
        {
            // Helper: launch TTS render on background thread
            auto launchTTS=[&](bool saveToLib, bool saveAndPlay){
                if(strlen(g_ttsText)==0) return;
                if(g_ttsThread.joinable()) g_ttsThread.join();
                std::string text=g_ttsText;
                // Build sanitized filename from text (max 60 chars, replace invalid chars)
                std::string fname=text;
                if(fname.size()>60) fname=fname.substr(0,60);
                for(char& c:fname){
                    if(c=='/'||c=='\\'||c==':'||c=='*'||c=='?'||c=='"'||c=='<'||c=='>'||c=='|'||c=='\n'||c=='\r')
                        c='_';
                }
                // Trim trailing spaces/dots
                while(!fname.empty()&&(fname.back()==' '||fname.back()=='.'))
                    fname.pop_back();
                if(fname.empty()) fname="tts";
                g_ttsSaveFilename=fname;
                g_ttsSaveToLib=saveToLib;
                g_ttsSaveAndPlay=saveAndPlay;
                g_ttsState.store(TTSState::Rendering);
                g_showTTSPopup=false; // Close popup - status shown in notification overlay
                g_ttsThread=std::thread([text](){
                    std::string escaped=text;
                    for(size_t p=0;(p=escaped.find("'",p))!=std::string::npos;p+=2)
                        escaped.replace(p,1,"''");
                    char tmpPath[MAX_PATH]={};
                    GetTempPathA(MAX_PATH,tmpPath);
                    std::string wavPath=std::string(tmpPath)+"voicedj_tts.wav";
                    std::string cmd="powershell -NoProfile -NonInteractive -Command \""
                        "Add-Type -AssemblyName System.Speech;"
                        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                        "$s.SetOutputToWaveFile([System.IO.Path]::GetFullPath('"+wavPath+"'));"
                        "$s.Speak('"+escaped+"');"
                        "$s.SetOutputToNull();"
                        "$s.Dispose()\"";
                    STARTUPINFOA si={sizeof(si)}; PROCESS_INFORMATION pi;
                    si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_HIDE;
                    BOOL ok=CreateProcessA(nullptr,(LPSTR)cmd.c_str(),nullptr,nullptr,FALSE,
                        CREATE_NO_WINDOW,nullptr,nullptr,&si,&pi);
                    if(ok){
                        WaitForSingleObject(pi.hProcess,8000);
                        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
                        // Verify WAV was created
                        DWORD attr=GetFileAttributesA(wavPath.c_str());
                        if(attr!=INVALID_FILE_ATTRIBUTES){
                            g_ttsPendingWav=wavPath;
                            g_ttsState.store(TTSState::Done);
                        } else {
                            g_ttsState.store(TTSState::Error);
                        }
                    } else {
                        g_ttsState.store(TTSState::Error);
                    }
                });
            };

            // FIX #1: All three buttons work correctly
            if(ImGui::Button("Speak",{80,0})||enter) launchTTS(false,false);
            ImGui::SameLine();
            if(ImGui::Button("Save to Library",{120,0})) launchTTS(true,false);
            ImGui::SameLine();
            // FIX #2: New "Play TTS & Save to Music" button
            ImGui::PushStyleColor(ImGuiCol_Button,{0.15f,0.45f,0.15f,1.0f});
            ImGui::PushStyleColor(ImGuiCol_ButtonHovered,{0.2f,0.65f,0.2f,1.0f});
            if(ImGui::Button("Play & Save",{90,0})) launchTTS(true,true);
            ImGui::PopStyleColor(2);
            ImGui::SameLine();
            if(ImGui::Button("Cancel",{70,0})){ g_showTTSPopup=false; }
        }
        ImGui::End();
    }
    tts_end:;

    // ── Notification overlay ──────────────────────────────────────────────────
    if(g_notifTimer>0.0f){
        g_notifTimer-=io.DeltaTime;
        float alpha=std::min(1.0f,g_notifTimer*2.0f);
        ImGui::SetNextWindowBgAlpha(0.85f*alpha);
        ImGui::SetNextWindowPos({io.DisplaySize.x/2,40},ImGuiCond_Always,{0.5f,0.0f});
        ImGui::SetNextWindowSize({0,0});
        ImGui::Begin("##notif",nullptr,
            ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoInputs|
            ImGuiWindowFlags_NoNav|ImGuiWindowFlags_NoMove|
            ImGuiWindowFlags_NoSavedSettings|ImGuiWindowFlags_NoBringToFrontOnFocus);
        ImGui::TextColored({1.0f,1.0f,0.4f,alpha},"%s",g_notifText.c_str());
        ImGui::End();
    }
}

// ─── D3D11 Setup ─────────────────────────────────────────────────────────────
static ID3D11Device*           g_pd3dDevice=nullptr;
static ID3D11DeviceContext*    g_pd3dCtx=nullptr;
static IDXGISwapChain*         g_pSwapChain=nullptr;
static ID3D11RenderTargetView* g_pRTV=nullptr;

static bool createD3D(HWND hwnd){
    DXGI_SWAP_CHAIN_DESC sd={};
    sd.BufferCount=2; sd.BufferDesc.Width=0; sd.BufferDesc.Height=0;
    sd.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferDesc.RefreshRate.Numerator=60; sd.BufferDesc.RefreshRate.Denominator=1;
    sd.Flags=DXGI_SWAP_CHAIN_FLAG_ALLOW_MODE_SWITCH;
    sd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow=hwnd; sd.SampleDesc.Count=1; sd.Windowed=TRUE;
    sd.SwapEffect=DXGI_SWAP_EFFECT_DISCARD;
    D3D_FEATURE_LEVEL fl; const D3D_FEATURE_LEVEL fls[]={D3D_FEATURE_LEVEL_11_0};
    HRESULT hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,0,
        fls,1,D3D11_SDK_VERSION,&sd,&g_pSwapChain,&g_pd3dDevice,&fl,&g_pd3dCtx);
    if(FAILED(hr)) return false;
    ID3D11Texture2D* pBB=nullptr;
    g_pSwapChain->GetBuffer(0,IID_PPV_ARGS(&pBB));
    g_pd3dDevice->CreateRenderTargetView(pBB,nullptr,&g_pRTV);
    pBB->Release();
    return true;
}
static void cleanupD3D(){
    if(g_pRTV){g_pRTV->Release();g_pRTV=nullptr;}
    if(g_pSwapChain){g_pSwapChain->Release();g_pSwapChain=nullptr;}
    if(g_pd3dCtx){g_pd3dCtx->Release();g_pd3dCtx=nullptr;}
    if(g_pd3dDevice){g_pd3dDevice->Release();g_pd3dDevice=nullptr;}
}
static void createRTV(){
    ID3D11Texture2D* pBB=nullptr;
    g_pSwapChain->GetBuffer(0,IID_PPV_ARGS(&pBB));
    g_pd3dDevice->CreateRenderTargetView(pBB,nullptr,&g_pRTV);
    pBB->Release();
}

// ─── Window Proc ─────────────────────────────────────────────────────────────
static LRESULT WINAPI WndProc(HWND hWnd,UINT msg,WPARAM wParam,LPARAM lParam){
    if(ImGui_ImplWin32_WndProcHandler(hWnd,msg,wParam,lParam)) return true;
    switch(msg){
    case WM_SIZE:
        if(g_pd3dDevice&&wParam!=SIZE_MINIMIZED){
            if(g_pRTV){g_pRTV->Release();g_pRTV=nullptr;}
            g_pSwapChain->ResizeBuffers(0,(UINT)LOWORD(lParam),(UINT)HIWORD(lParam),
                DXGI_FORMAT_UNKNOWN,0);
            createRTV();
        }
        return 0;
    case WM_HOTKEY:
        // Ctrl+0..9 binds
        if(wParam>=100&&wParam<=109){
            int slot=(int)(wParam-100);
            if(g_settings.binds.count(slot)){
                for(auto& e:g_musicList){
                    if(e.name==g_settings.binds[slot]){
                        if(g_settings.stackableAudio){
                            // Stackable mode: load audio into a new ClipInstance and push to stack
                            // We need to load the file into a temporary buffer
                            std::vector<float> tmpBuf;
                            {
                                // Load into temp buffer (reuse loadAudioFile logic inline)
                                // We do this by loading normally then stealing the buffer
                                if(loadAudioFile(e.path)){
                                    std::lock_guard<std::mutex> lk2(g_musicMtx);
                                    tmpBuf=g_musicBuf;
                                    g_musicBuf.clear(); g_musicLoaded=false;
                                }
                            }
                            if(!tmpBuf.empty()){
                                std::lock_guard<std::mutex> lk2(g_clipStackMtx);
                                g_clipStack.push_back({std::move(tmpBuf),0});
                                showNotif(("Stack+"+std::to_string(slot)+": "+e.name).c_str());
                            }
                        } else {
                            if(loadAudioFile(e.path)){
                                g_isClipPlaying.store(true);
                                g_playState.store(PlayState::Playing);
                                showNotif(("Bind "+std::to_string(slot)+": "+e.name).c_str());
                            }
                        }
                        break;
                    }
                }
            }
        }
        // Ctrl+Tab = TTS popup toggle.
        // When opening: bring window to front so TTS popup is visible.
        // When already open: just close it (toggle). Do NOT re-raise the main window.
        if(wParam==200){
            if(!g_showTTSPopup){
                // Clear previous TTS text when opening fresh
                memset(g_ttsText,0,sizeof(g_ttsText));
                g_showTTSPopup=true;
                g_ttsJustOpened=true;
                // Bring VoiceDJ window to foreground so the TTS popup is visible.
                // Use AttachThreadInput trick to bypass Windows foreground lock.
                if(g_hwnd){
                    HWND hFg=GetForegroundWindow();
                    DWORD fgTid=GetWindowThreadProcessId(hFg,nullptr);
                    DWORD myTid=GetCurrentThreadId();
                    if(fgTid && fgTid!=myTid) AttachThreadInput(fgTid,myTid,TRUE);
                    ShowWindow(g_hwnd,SW_RESTORE); // restore if minimized
                    SetWindowPos(g_hwnd,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);
                    SetForegroundWindow(g_hwnd);
                    SetWindowPos(g_hwnd,HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);
                    if(fgTid && fgTid!=myTid) AttachThreadInput(fgTid,myTid,FALSE);
                }
            } else {
                // Already open: toggle closed. Do NOT re-raise the window.
                g_showTTSPopup=false;
            }
        }
        return 0;
    case WM_SYSCOMMAND:
        if((wParam&0xfff0)==SC_KEYMENU) return 0;
        break;
    case WM_DESTROY:
        PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(hWnd,msg,wParam,lParam);
}

// ─── WinMain ─────────────────────────────────────────────────────────────────
int WINAPI WinMain(HINSTANCE hInst,HINSTANCE,LPSTR,int){
    // Get app directory
    char exePath[MAX_PATH]={};
    GetModuleFileNameA(nullptr,exePath,MAX_PATH);
    std::string appDir=std::string(exePath);
    appDir=appDir.substr(0,appDir.find_last_of("\\/"));
    std::string musicDir=appDir+"\\music";
    std::filesystem::create_directories(musicDir);
    g_musicDirGlobal=musicDir;

    // Init miniaudio
    if(ma_context_init(nullptr,0,nullptr,&g_maCtx)!=MA_SUCCESS){
        MessageBoxA(nullptr,"Failed to initialize audio context!","Error",MB_OK|MB_ICONERROR);
        return 1;
    }
    enumerateDevices();

    // Auto-select VB-Cable output
    for(int i=0;i<(int)g_outputDevNames.size();i++){
        if(g_outputDevNames[i].find("CABLE Input")!=std::string::npos||
           g_outputDevNames[i].find("VB-Audio")!=std::string::npos){
            g_settings.outputDeviceIndex=i; break;
        }
    }

    // Init SoundTouch
    g_st.setSampleRate(SAMPLE_RATE);
    g_st.setChannels(CHANNELS);
    g_st.setPitchSemiTones(0.0f);
    g_st.setSetting(SETTING_USE_QUICKSEEK,1);
    g_st.setSetting(SETTING_SEQUENCE_MS,40);
    g_st.setSetting(SETTING_SEEKWINDOW_MS,15);
    g_st.setSetting(SETTING_OVERLAP_MS,8);

     // Init effects (mic chain)
    g_reverb.init(SAMPLE_RATE);
    g_robot.init();
    g_echo.init();
    // Init effects (music chain)
    g_mReverb.init(SAMPLE_RATE);
    g_mRobot.init();
    g_mEcho.init();
    // Init effects (monitor chain - dedicated instances to avoid thread conflicts)
    g_monReverb.init(SAMPLE_RATE);
    g_monRobot.init();
    g_monEcho.init();
    // Init monitor SoundTouch
    g_monSt.setSampleRate(SAMPLE_RATE);
    g_monSt.setChannels(CHANNELS);
    g_monSt.setPitchSemiTones(0.0f);
    g_monSt.setSetting(SETTING_USE_QUICKSEEK,1);
    g_monSt.setSetting(SETTING_SEQUENCE_MS,40);
    g_monSt.setSetting(SETTING_SEEKWINDOW_MS,15);
    g_monSt.setSetting(SETTING_OVERLAP_MS,8);
    // Init music SoundTouch
    g_mSt.setSampleRate(SAMPLE_RATE);
    g_mSt.setChannels(CHANNELS);
    g_mSt.setPitchSemiTones(0.0f);
    g_mSt.setSetting(SETTING_USE_QUICKSEEK,1);
    g_mSt.setSetting(SETTING_SEQUENCE_MS,40);
    g_mSt.setSetting(SETTING_SEEKWINDOW_MS,15);
    g_mSt.setSetting(SETTING_OVERLAP_MS,8);
    updateEffects();
    // Load settings
    loadSettings(appDir+"\\settings.json");
    updateEffects();
    updateMusicEffects();

    // Scan music
    scanMusicDir(musicDir);

    // Init binds array
    for(int i=0;i<10;i++) g_bindTrack[i]=-1;

    // Create window
    // FIX #5: Load icon from embedded resource (IDI_APPLICATION = 32512 = standard)
    // The resource file embeds icon.ico which is loaded by Windows automatically
    HICON hIcon=LoadIconW(hInst,MAKEINTRESOURCEW(1));
    if(!hIcon) hIcon=LoadIconW(nullptr,IDI_APPLICATION);

    WNDCLASSEXW wc={sizeof(wc),CS_CLASSDC,WndProc,0,0,hInst,
        hIcon,LoadCursor(nullptr,IDC_ARROW),
        nullptr,nullptr,L"VoiceDJClass",hIcon};
    RegisterClassExW(&wc);
    // Start maximized so all panels fit without needing to resize
    HWND hwnd=CreateWindowExW(0,L"VoiceDJClass",
        L"VoiceDJ for CS  —  v2.12",
        WS_OVERLAPPEDWINDOW,100,100,1280,900,nullptr,nullptr,hInst,nullptr);
    if(!hwnd){MessageBoxA(nullptr,"Failed to create window","Error",MB_OK);return 1;}
    g_hwnd=hwnd;
    if(!createD3D(hwnd)){
        MessageBoxA(nullptr,"Failed to create D3D11 device","Error",MB_OK);
        return 1;
    }
    ShowWindow(hwnd,SW_MAXIMIZE);
    UpdateWindow(hwnd);

    // Register global hotkeys
    for(int i=0;i<10;i++)
        RegisterHotKey(hwnd,100+i,MOD_CONTROL,0x30+i);
    RegisterHotKey(hwnd,200,MOD_CONTROL,VK_TAB);

    // Init ImGui
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io=ImGui::GetIO();
    io.ConfigFlags|=ImGuiConfigFlags_NavEnableKeyboard;
    io.IniFilename=nullptr;  // Don't save imgui.ini
    applyDarkTheme();

    // Load font
    ImFontConfig fc; fc.OversampleH=2; fc.OversampleV=2;
    io.Fonts->AddFontDefault(&fc);

    ImGui_ImplWin32_Init(hwnd);
    ImGui_ImplDX11_Init(g_pd3dDevice,g_pd3dCtx);

    // PTT polling thread
    g_pttRunning=true;
    g_pttThread=std::thread([]{
        while(g_pttRunning.load()){
            g_pttActive=(GetAsyncKeyState(VK_XBUTTON1)&0x8000)!=0;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    });

    // Check for VB-Cable
    bool hasVBCable=false;
    for(auto& n:g_outputDevNames){
        if(n.find("CABLE")!=std::string::npos||n.find("VB-Audio")!=std::string::npos){
            hasVBCable=true; break;
        }
    }
    if(!hasVBCable){
        int r=MessageBoxA(hwnd,
            "VB-Audio Virtual Cable was not detected!\n\n"
            "This app requires VB-Cable to route audio into CS voice chat.\n\n"
            "Click YES to open the download page (it's free),\n"
            "then install it and restart this app.\n\n"
            "Click NO to continue anyway.",
            "VB-Cable Not Found",MB_YESNO|MB_ICONWARNING);
        if(r==IDYES)
            ShellExecuteA(nullptr,"open","https://vb-audio.com/Cable/",nullptr,nullptr,SW_SHOW);
    }

    // Main loop
    MSG msg;
    bool running=true;
    while(running){
        while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)){
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
            if(msg.message==WM_QUIT) running=false;
        }
        if(!running) break;

        ImGui_ImplDX11_NewFrame();
        ImGui_ImplWin32_NewFrame();
        ImGui::NewFrame();

        renderUI(appDir,musicDir);

        ImGui::Render();
        const float cc[4]={0.08f,0.08f,0.10f,1.0f};
        g_pd3dCtx->OMSetRenderTargets(1,&g_pRTV,nullptr);
        g_pd3dCtx->ClearRenderTargetView(g_pRTV,cc);
        ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
        g_pSwapChain->Present(1,0);
    }

    // Cleanup
    g_pttRunning=false;
    if(g_pttThread.joinable()) g_pttThread.join();
    if(g_ytThread.joinable()) g_ytThread.join();
    if(g_ttsThread.joinable()) g_ttsThread.join();
    stopDevices();
    ma_context_uninit(&g_maCtx);
    saveSettings(appDir+"\\settings.json");

    // Unregister hotkeys
    for(int i=0;i<10;i++) UnregisterHotKey(hwnd,100+i);
    UnregisterHotKey(hwnd,200);

    ImGui_ImplDX11_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();
    cleanupD3D();
    DestroyWindow(hwnd);
    UnregisterClassW(L"VoiceDJClass",hInst);

    return 0;
}
