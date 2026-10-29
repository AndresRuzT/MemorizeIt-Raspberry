import pygame
import numpy as np

class SoundSystem:
    def __init__(self):
        self.initialized = False
        self.panel_sounds = []
        self.success_sound = None
        self.error_sound = None

    def init(self):
        if self.initialized:
            return

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024)
            self.initialized = True

            # Frecuencias para los 9 paneles (Do4 a Re5)
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
            print(f"[SoundSystem] Aviso: No se pudo inicializar audio ({e}). El juego correrá en silencio.")
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

        # Envolvente para evitar chasquidos acústicos
        fade_samples = int(sample_rate * 0.02)
        envelope = np.ones(n_samples, dtype=np.float32)
        if fade_samples > 0:
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)

        if waveform == 'sine':
            wave = np.sin(2 * np.pi * frequency * t)
        else:
            # Onda cuadrada suave para zumbador de error
            wave = np.sign(np.sin(2 * np.pi * frequency * t)) * 0.65

        audio_data = (wave * envelope * 32000.0).astype(np.int16)
        try:
            return pygame.sndarray.make_sound(audio_data)
        except Exception:
            return None
