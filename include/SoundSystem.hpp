#pragma once

#include "raylib.h"
#include <vector>

class SoundSystem {
public:
    SoundSystem();
    ~SoundSystem();

    void init();
    void cleanup();

    void playPanelTone(int panelIndex);
    void playSuccessChime();
    void playErrorBuzzer();

private:
    bool initialized{false};
    std::vector<Sound> panelSounds;
    Sound successSound{};
    Sound errorSound{};

    Sound createTone(float frequency, float duration, int waveformType);
};
