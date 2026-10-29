#include "SoundSystem.hpp"
#include <cmath>
#include <cstdlib>

SoundSystem::SoundSystem() {}

SoundSystem::~SoundSystem() {
    cleanup();
}

void SoundSystem::init() {
    if (initialized) return;

    InitAudioDevice();
    initialized = true;

    // Frecuencias pentatónicas y diatónicas agradables para los 9 paneles (estilo Simon / Among Us)
    const float frequencies[9] = {
        261.63f, // Do (C4)
        293.66f, // Re (D4)
        329.63f, // Mi (E4)
        349.23f, // Fa (F4)
        392.00f, // Sol (G4)
        440.00f, // La (A4)
        493.88f, // Si (B4)
        523.25f, // Do (C5)
        587.33f  // Re (D5)
    };

    panelSounds.resize(9);
    for (int i = 0; i < 9; ++i) {
        panelSounds[i] = createTone(frequencies[i], 0.28f, 0); // Seno con decaimiento
    }

    successSound = createTone(880.0f, 0.45f, 0); // Chime brillante
    errorSound = createTone(110.0f, 0.50f, 1);   // Zumbador grave (onda cuadrada)
}

void SoundSystem::cleanup() {
    if (!initialized) return;

    for (auto& snd : panelSounds) {
        UnloadSound(snd);
    }
    panelSounds.clear();

    UnloadSound(successSound);
    UnloadSound(errorSound);

    CloseAudioDevice();
    initialized = false;
}

void SoundSystem::playPanelTone(int panelIndex) {
    if (!initialized || panelIndex < 0 || panelIndex >= static_cast<int>(panelSounds.size())) return;
    PlaySound(panelSounds[panelIndex]);
}

void SoundSystem::playSuccessChime() {
    if (!initialized) return;
    PlaySound(successSound);
}

void SoundSystem::playErrorBuzzer() {
    if (!initialized) return;
    PlaySound(errorSound);
}

Sound SoundSystem::createTone(float frequency, float duration, int waveformType) {
    const int sampleRate = 44100;
    const int frameCount = static_cast<int>(sampleRate * duration);

    Wave wave{};
    wave.frameCount = frameCount;
    wave.sampleRate = sampleRate;
    wave.sampleSize = 16;
    wave.channels = 1;

    short* samples = static_cast<short*>(std::malloc(frameCount * sizeof(short)));

    const float pi = 3.14159265358979323846f;
    const float fadeDuration = 0.025f;

    for (int i = 0; i < frameCount; ++i) {
        float t = static_cast<float>(i) / sampleRate;

        // Envolvente de volumen (Fade in y Fade out) para evitar clics acústicos
        float envelope = 1.0f;
        if (t < fadeDuration) {
            envelope = t / fadeDuration;
        } else if (t > duration - fadeDuration) {
            envelope = (duration - t) / fadeDuration;
        }

        float sampleVal = 0.0f;
        if (waveformType == 0) {
            // Onda senoidal pura
            sampleVal = std::sin(2.0f * pi * frequency * t);
        } else {
            // Onda cuadrada suave con armónicos (sonido de error estilo arcade)
            float phase = std::fmod(t * frequency, 1.0f);
            sampleVal = (phase < 0.5f) ? 0.6f : -0.6f;
        }

        samples[i] = static_cast<short>(sampleVal * envelope * 28000.0f);
    }

    wave.data = samples;
    Sound sound = LoadSoundFromWave(wave);
    UnloadWave(wave);

    return sound;
}
