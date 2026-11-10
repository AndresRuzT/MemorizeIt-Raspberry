import pygame
import numpy as np

class SoundSystem:
    def __init__(self):
        self.initialized = False
        self.panel_sounds = []
        self.success_sound = None
        self.error_sound = None
        self.beep_sound = None

    def init(self):
        if self.initialized:
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self.initialized = True

            # Frequencies for the 9 panels (C4 to D5)
            frequencies = [
                261.63, 293.66, 329.63,
                349.23, 392.00, 440.00,
                493.88, 523.25, 587.33
            ]

            self.panel_sounds = [self._create_tone(freq, 0.30, waveform='sine') for freq in frequencies]
            self.success_sound = self._create_tone(880.0, 0.45, waveform='sine')
            self.error_sound = self._create_tone(115.0, 0.50, waveform='square')
            self.beep_sound = self._create_tone(520.0, 0.12, waveform='sine')
        except Exception as e:
            print(f"[SoundSystem] Warning: Audio initialization failed ({e}). Running in silent mode.")
            self.initialized = False

    def play_countdown_beep(self):
        if self.initialized and self.beep_sound:
            self.beep_sound.play()

    def play_panel_tone(self, index):
        if not self.initialized or index < 0 or index >= len(self.panel_sounds):
            return
        if self.panel_sounds[index]:
            self.panel_sounds[index].play()

    def play_success_chime(self):
        if self.initialized and self.success_sound:
            self.success_sound.play()

    def play_error_buzzer(self):
        if self.initialized and self.error_sound:
            self.error_sound.play()

    def _create_tone(self, frequency, duration, waveform='sine'):
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)

        # Smooth envelope to avoid audio clicks
        fade_samples = int(sample_rate * 0.02)
        envelope = np.ones(n_samples, dtype=np.float32)
        if fade_samples > 0:
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)

        if waveform == 'sine':
            wave = np.sin(2 * np.pi * frequency * t)
        else:
            # Square wave for error buzzer
            wave = np.sign(np.sin(2 * np.pi * frequency * t)) * 0.65

        audio_data = (wave * envelope * 32000.0).astype(np.int16)

        mixer_init = pygame.mixer.get_init()
        channels = mixer_init[2] if mixer_init else 1
        if channels == 2:
            audio_data = np.column_stack((audio_data, audio_data))
        elif channels > 2:
            audio_data = np.repeat(audio_data[:, np.newaxis], channels, axis=1)

        try:
            return pygame.sndarray.make_sound(audio_data)
        except Exception as e:
            print(f"[SoundSystem] Error generating tone: {e}")
            return None
