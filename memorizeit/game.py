import pygame
import random
import math
from .grid import GridPanel, PanelState
from .vision import VisionTracker
from .audio import SoundSystem
from .scores import ScoreManager

class GameState:
    WAITING_START = 0   # Esperando dedo en el centro durante 5 segundos
    SHOW_SEQUENCE = 1   # Reproduciendo el patrón de paneles
    PLAYER_TURN = 2     # Turno del jugador (2 segundos por panel)
    ROUND_WON = 3       # Acierto de ronda
    GAME_OVER = 4       # Fallo y registro de récord

class GameEngine:
    def __init__(self, screen_width=1280, screen_height=720, camera_index=None):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.vision = VisionTracker(camera_index=camera_index, width=640, height=480)
        self.sound = SoundSystem()
        self.score_mgr = ScoreManager()

        # Posicionamiento de columnas (Izquierda: Tablero, Derecha: Cámara y Récords)
        grid_size = 500
        grid_x = 55
        grid_y = 110
        self.grid = GridPanel(pygame.Rect(grid_x, grid_y, grid_size, grid_size), spacing=16)

        # Dimensiones de la cámara en la columna derecha
        self.cam_w = 600
        self.cam_h = 450
        self.cam_x = 625
        self.cam_y = 90

        # Tarjeta de récords inferior derecha
        self.card_rect = pygame.Rect(self.cam_x, self.cam_y + self.cam_h + 16, self.cam_w, 135)

        # Estado inicial
        self.state = GameState.WAITING_START
        self.current_round = 1
        self.full_sequence = []
        self.player_step = 0

        # Temporizadores de inicio con dedo en el centro (5 segundos)
        self.center_dwell_time = 5.0
        self.center_hover_duration = 0.0
        self.last_beep_second = 6

        # Temporizadores de reproducción
        self.timer = 0.0
        self.sequence_step = 0
        self.is_step_flashing = False

        # Temporizador de interacción del juego (2.0 segundos continuos)
        self.required_dwell_time = 2.0
        self.hover_duration = 0.0
        self.current_hovered_panel = -1
        self.debounce_cooldown = 0.0
        self.debounce_cooldown_time = 0.50

        # Control de Game Over
        self.game_over_timer = 0.0
        self.is_new_record = False

        # Tipografías
        self.font_title = None
        self.font_large = None
        self.font_med = None
        self.font_small = None
        self.font_mono = None

    def initialize(self):
        self.sound.init()
        self.vision.start()
        self.score_mgr.load()

        pygame.font.init()
        self.font_title = pygame.font.SysFont("sans-serif", 32, bold=True)
        self.font_large = pygame.font.SysFont("sans-serif", 24, bold=True)
        self.font_med = pygame.font.SysFont("sans-serif", 20, bold=True)
        self.font_small = pygame.font.SysFont("sans-serif", 14, bold=True)
        self.font_mono = pygame.font.SysFont("monospace", 14, bold=True)

    def start_infinite_game(self):
        """Inicia una nueva partida infinita tras el conteo de 5s."""
        self.current_round = 1
        self.player_step = 0
        self.full_sequence = [random.randint(0, 8)]  # Empieza con 1 panel
        self.start_round(1)

    def start_round(self, round_num):
        self.current_round = round_num
        self.player_step = 0
        self.sequence_step = 0
        self.is_step_flashing = False
        self.timer = 0.6
        self.current_hovered_panel = -1
        self.hover_duration = 0.0
        self.state = GameState.SHOW_SEQUENCE

    def update(self, dt):
        self.grid.update(dt)

        if self.debounce_cooldown > 0.0:
            self.debounce_cooldown -= dt

        # Posición del dedo normalizada (0.0 a 1.0)
        finger = self.vision.get_fingertip()
        pointer_active = False
        norm_x, norm_y = 0.5, 0.5

        if finger.detected:
            norm_x, norm_y = finger.norm_x, finger.norm_y
            pointer_active = True
        elif pygame.mouse.get_pressed()[0]:
            # Fallback interactivo con ratón
            mx, my = pygame.mouse.get_pos()
            if self.grid.area_rect.collidepoint(mx, my):
                norm_x = (mx - self.grid.area_rect.x) / self.grid.area_rect.width
                norm_y = (my - self.grid.area_rect.y) / self.grid.area_rect.height
                pointer_active = True
            elif pygame.Rect(self.cam_x, self.cam_y, self.cam_w, self.cam_h).collidepoint(mx, my):
                norm_x = (mx - self.cam_x) / self.cam_w
                norm_y = (my - self.cam_y) / self.cam_h
                pointer_active = True

        # Convertir a coordenadas sobre el tablero
        grid_pixel_pos = (
            int(self.grid.area_rect.x + norm_x * self.grid.area_rect.width),
            int(self.grid.area_rect.y + norm_y * self.grid.area_rect.height)
        )

        # MÁQUINA DE ESTADOS
        if self.state == GameState.WAITING_START:
            self._update_waiting_start(dt, pointer_active, norm_x, norm_y)

        elif self.state == GameState.SHOW_SEQUENCE:
            self._update_show_sequence(dt)

        elif self.state == GameState.PLAYER_TURN:
            self._update_player_turn(dt, pointer_active, grid_pixel_pos, norm_x, norm_y)

        elif self.state == GameState.ROUND_WON:
            self.timer -= dt
            if self.timer <= 0.0:
                # Añadir un nuevo paso a la secuencia para hacerla infinita
                self.full_sequence.append(random.randint(0, 8))
                self.start_round(self.current_round + 1)

        elif self.state == GameState.GAME_OVER:
            self.game_over_timer -= dt
            if self.game_over_timer <= 0.0:
                # Regresar automáticamente a estado de espera
                self.state = GameState.WAITING_START
                self.center_hover_duration = 0.0
                self.last_beep_second = 6

        return pointer_active, norm_x, norm_y

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                self.vision.cycle_camera()
            elif event.key == pygame.K_b:
                self.vision.recalibrate_background()
            elif event.key == pygame.K_r:
                self.state = GameState.WAITING_START
                self.center_hover_duration = 0.0
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self.state == GameState.GAME_OVER:
                    self.state = GameState.WAITING_START
                    self.center_hover_duration = 0.0
                elif self.state == GameState.WAITING_START:
                    self.start_infinite_game()

    def _update_waiting_start(self, dt, pointer_active, norm_x, norm_y):
        # La zona central corresponde a norm_x entre 0.35-0.65 y norm_y entre 0.35-0.65
        in_center = pointer_active and (0.33 <= norm_x <= 0.67) and (0.33 <= norm_y <= 0.67)

        if in_center:
            self.center_hover_duration += dt
            sec_rem = int(math.ceil(max(0.0, self.center_dwell_time - self.center_hover_duration)))

            if 1 <= sec_rem <= 5 and sec_rem != self.last_beep_second:
                self.last_beep_second = sec_rem
                self.sound.play_countdown_beep()

            # Completados los 5 segundos con el dedo en el centro
            if self.center_hover_duration >= self.center_dwell_time:
                self.sound.play_success_chime()
                self.start_infinite_game()
        else:
            # Si retira el dedo del centro antes de los 5s, reiniciar conteo
            self.center_hover_duration = 0.0
            self.last_beep_second = 6

    def _update_show_sequence(self, dt):
        self.timer -= dt
        if self.timer <= 0.0:
            if not self.is_step_flashing:
                if self.sequence_step < len(self.full_sequence):
                    panel_to_flash = self.full_sequence[self.sequence_step]
                    self.grid.set_panel_state(panel_to_flash, PanelState.FLASHING, duration=0.55)
                    self.sound.play_panel_tone(panel_to_flash)
                    self.is_step_flashing = True
                    self.timer = 0.55
                else:
                    # Fin de la secuencia: turno del jugador
                    self.state = GameState.PLAYER_TURN
                    self.player_step = 0
                    self.current_hovered_panel = -1
                    self.hover_duration = 0.0
                    self.debounce_cooldown = 0.35
            else:
                self.is_step_flashing = False
                self.sequence_step += 1
                self.timer = 0.22

    def _update_player_turn(self, dt, pointer_active, grid_pixel_pos, norm_x, norm_y):
        # Determinar el panel en base a las coordenadas del dedo (0 a 8)
        hovered = -1
        if pointer_active:
            col = int(norm_x * 3)
            row = int(norm_y * 3)
            col = max(0, min(2, col))
            row = max(0, min(2, row))
            hovered = row * 3 + col

        for i in range(9):
            if i == hovered:
                self.grid.set_panel_state(i, PanelState.HOVERED, duration=0.05)

        if hovered != -1 and self.debounce_cooldown <= 0.0:
            if hovered == self.current_hovered_panel:
                self.hover_duration += dt
                # Confirmar tras 2.0 segundos continuos
                if self.hover_duration >= self.required_dwell_time:
                    self._trigger_panel_press(hovered)
                    self.hover_duration = 0.0
                    self.debounce_cooldown = self.debounce_cooldown_time
            else:
                self.current_hovered_panel = hovered
                self.hover_duration = 0.0
        else:
            self.current_hovered_panel = -1
            self.hover_duration = 0.0

    def _trigger_panel_press(self, index):
        expected = self.full_sequence[self.player_step]

        if index == expected:
            # Acierto parcial
            self.grid.set_panel_state(index, PanelState.PRESSED, duration=0.35)
            self.sound.play_panel_tone(index)
            self.player_step += 1

            if self.player_step >= len(self.full_sequence):
                # ¡Ronda completada con éxito!
                self.state = GameState.ROUND_WON
                self.timer = 0.90
                self.grid.set_all_state(PanelState.SUCCESS, duration=0.65)
                self.sound.play_success_chime()

                # Actualizar récord inmediatamente si se superó
                self.is_new_record = self.score_mgr.add_score("Tripulante", self.current_round)
        else:
            # ¡Fallo en el reactor! (Game Over)
            self.state = GameState.GAME_OVER
            self.game_over_timer = 3.8
            self.grid.set_all_state(PanelState.ERROR, duration=1.0)
            self.sound.play_error_buzzer()

            # Guardar puntuación final
            self.is_new_record = self.score_mgr.add_score("Tripulante", self.current_round)

    def draw(self, surface, pointer_active, norm_x, norm_y):
        surface.fill((12, 16, 24))

        # 1. Barra superior
        pygame.draw.rect(surface, (18, 24, 34), (0, 0, self.screen_width, 60))
        pygame.draw.line(surface, (40, 56, 80), (0, 60), (self.screen_width, 60), 2)

        title_surf = self.font_title.render("REACTOR MEMORY", True, (160, 220, 255))
        surface.blit(title_surf, (35, 14))

        # Indicador de Ronda y Récord
        if self.state in (GameState.SHOW_SEQUENCE, GameState.PLAYER_TURN, GameState.ROUND_WON):
            round_text = f"RONDA: {self.current_round}"
            r_surf = self.font_large.render(round_text, True, (255, 220, 60))
            surface.blit(r_surf, (360, 18))

        rec_str = f"RECORD MUNDIAL: Ronda {self.score_mgr.best_round} ({self.score_mgr.best_player})"
        rec_surf = self.font_large.render(rec_str, True, (50, 240, 140))
        surface.blit(rec_surf, (self.screen_width - rec_surf.get_width() - 35, 18))

        # 2. Dibujar Tablero de Juego (Columna Izquierda)
        charging_idx = self.current_hovered_panel if self.state == GameState.PLAYER_TURN else -1
        charging_prog = min(1.0, self.hover_duration / self.required_dwell_time)
        self.grid.draw(surface, charging_index=charging_idx, charging_progress=charging_prog)

        # 3. Mensaje de estado inferior (debajo del tablero)
        self._draw_status_banner(surface)

        # 4. Columna Derecha: Vista de Cámara en Vivo con Cuadrícula Superpuesta
        self._draw_camera_column(surface, pointer_active, norm_x, norm_y)

        # 5. Cursor visual y Anillo de Carga sobre el tablero
        if pointer_active:
            grid_px = int(self.grid.area_rect.x + norm_x * self.grid.area_rect.width)
            grid_py = int(self.grid.area_rect.y + norm_y * self.grid.area_rect.height)

            pygame.draw.circle(surface, (0, 255, 220), (grid_px, grid_py), 14)
            pygame.draw.circle(surface, (255, 255, 255), (grid_px, grid_py), 18, width=2)

            if self.state == GameState.PLAYER_TURN and self.current_hovered_panel != -1 and self.hover_duration > 0.0:
                prog = min(1.0, self.hover_duration / self.required_dwell_time)
                arc_rect = pygame.Rect(grid_px - 28, grid_py - 28, 56, 56)
                start_angle = -math.pi / 2
                stop_angle = start_angle + (2 * math.pi * prog)
                if stop_angle > start_angle:
                    pygame.draw.arc(surface, (255, 220, 40), arc_rect, -stop_angle, -start_angle, 4)

                rem_sec = max(0.0, self.required_dwell_time - self.hover_duration)
                rem_text = self.font_small.render(f"{rem_sec:.1f}s", True, (255, 240, 100))
                surface.blit(rem_text, (grid_px + 24, grid_py - 10))

    def _draw_status_banner(self, surface):
        msg = ""
        col = (255, 255, 255)

        if self.state == GameState.WAITING_START:
            if self.center_hover_duration > 0.0:
                rem = max(0.0, self.center_dwell_time - self.center_hover_duration)
                msg = f"INICIANDO EN: {rem:.1f}s  (Manten el dedo en el centro)"
                col = (255, 225, 60)
            else:
                msg = "COLOCA TU DEDO EN EL CENTRO DE LA CAMARA DURANTE 5s"
                col = (180, 225, 255)

        elif self.state == GameState.SHOW_SEQUENCE:
            msg = f"MEMORIZA EL PATRON... (Paso {self.sequence_step + 1}/{len(self.full_sequence)})"
            col = (255, 215, 0)

        elif self.state == GameState.PLAYER_TURN:
            if self.current_hovered_panel != -1 and self.hover_duration > 0.0:
                rem = max(0.0, self.required_dwell_time - self.hover_duration)
                msg = f"MANTEN EL DEDO: {self.hover_duration:.1f}s / {self.required_dwell_time:.1f}s  (Faltan {rem:.1f}s)"
                col = (255, 235, 80)
            else:
                msg = f"TU TURNO: Toca el panel {self.player_step + 1}/{len(self.full_sequence)} (Manten 2s)"
                col = (80, 235, 255)

        elif self.state == GameState.ROUND_WON:
            msg = f"CORRECTO! RONDA {self.current_round} SUPERADA"
            col = (50, 240, 120)

        elif self.state == GameState.GAME_OVER:
            msg = f"GAME OVER - REACTOR BLOQUEADO! (Llegaste a la Ronda {self.current_round})"
            col = (255, 60, 70)

        banner_rect = pygame.Rect(self.grid.area_rect.x - 10, self.grid.area_rect.bottom + 16, self.grid.area_rect.width + 20, 48)
        pygame.draw.rect(surface, (18, 24, 34), banner_rect, border_radius=8)
        pygame.draw.rect(surface, (40, 56, 80), banner_rect, width=2, border_radius=8)

        txt_surf = self.font_med.render(msg, True, col)
        surface.blit(txt_surf, (banner_rect.centerx - txt_surf.get_width() // 2, banner_rect.centery - txt_surf.get_height() // 2))

    def _draw_camera_column(self, surface, pointer_active, norm_x, norm_y):
        # Marco de la cámara
        cam_outer = pygame.Rect(self.cam_x - 4, self.cam_y - 4, self.cam_w + 8, self.cam_h + 8)
        pygame.draw.rect(surface, (20, 28, 40), cam_outer, border_radius=12)
        pygame.draw.rect(surface, (50, 70, 95), cam_outer, width=3, border_radius=12)

        # Obtener superficie continua de la cámara (sin parpadeos)
        preview_surf = self.vision.get_preview_surface(self.cam_w, self.cam_h)
        if preview_surf is not None:
            surface.blit(preview_surf, (self.cam_x, self.cam_y))
        else:
            pygame.draw.rect(surface, (0, 0, 0), (self.cam_x, self.cam_y, self.cam_w, self.cam_h), border_radius=10)

        # Superponer cuadrícula 3x3 semitransparente sobre la cámara
        cell_w = self.cam_w / 3.0
        cell_h = self.cam_h / 3.0
        for i in range(1, 3):
            pygame.draw.line(surface, (80, 160, 220, 120), (self.cam_x + i * cell_w, self.cam_y), (self.cam_x + i * cell_w, self.cam_y + self.cam_h), 1)
            pygame.draw.line(surface, (80, 160, 220, 120), (self.cam_x, self.cam_y + i * cell_h), (self.cam_x + self.cam_w, self.cam_y + i * cell_h), 1)

        # EN ESTADO DE ESPERA: Dibujar zona central de inicio (5 segundos)
        if self.state == GameState.WAITING_START:
            cx = self.cam_x + self.cam_w // 2
            cy = self.cam_y + self.cam_h // 2
            r = int(min(cell_w, cell_h) * 0.40)

            # Zona central brillante
            pygame.draw.circle(surface, (0, 230, 255), (cx, cy), r, width=3)

            if self.center_hover_duration > 0.0:
                prog = min(1.0, self.center_hover_duration / self.center_dwell_time)
                # Llenado del anillo de progreso
                arc_r = pygame.Rect(cx - r - 8, cy - r - 8, (r + 8) * 2, (r + 8) * 2)
                start_angle = -math.pi / 2
                stop_angle = start_angle + (2 * math.pi * prog)
                if stop_angle > start_angle:
                    pygame.draw.arc(surface, (255, 220, 40), arc_r, -stop_angle, -start_angle, 6)

                rem_sec = max(0.0, self.center_dwell_time - self.center_hover_duration)
                rem_txt = self.font_large.render(f"{rem_sec:.1f}s", True, (255, 230, 70))
                surface.blit(rem_txt, (cx - rem_txt.get_width() // 2, cy - rem_txt.get_height() // 2))
            else:
                lbl = self.font_small.render("INICIAR (5s)", True, (200, 255, 255))
                surface.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2))

        # Barra superior con nombre de la cámara actual
        title_box = pygame.Rect(self.cam_x, self.cam_y, self.cam_w, 28)
        bar_surf = pygame.Surface((title_box.width, title_box.height), pygame.SRCALPHA)
        bar_surf.fill((10, 15, 24, 215))
        surface.blit(bar_surf, (title_box.x, title_box.y))

        cam_name = f"CAM: {self.vision.get_camera_name()} [{self.vision.tracker_name}]"
        cam_lbl = self.font_small.render(cam_name, True, (200, 240, 255))
        surface.blit(cam_lbl, (self.cam_x + 10, self.cam_y + 6))

        switch_lbl = self.font_small.render("[C] Cambiar Cam  [Espacio] Iniciar", True, (255, 215, 80))
        surface.blit(switch_lbl, (self.cam_x + self.cam_w - switch_lbl.get_width() - 10, self.cam_y + 6))

        # Dedo sobre la cámara (Cursor espejo)
        if pointer_active:
            cpx = int(self.cam_x + norm_x * self.cam_w)
            cpy = int(self.cam_y + norm_y * self.cam_h)
            pygame.draw.circle(surface, (0, 255, 120), (cpx, cpy), 10)
            pygame.draw.circle(surface, (255, 255, 255), (cpx, cpy), 16, width=2)

        # 5. Tarjeta de Récords y Estadísticas (Debajo de la cámara)
        pygame.draw.rect(surface, (18, 24, 34), self.card_rect, border_radius=10)
        pygame.draw.rect(surface, (40, 56, 80), self.card_rect, width=2, border_radius=10)

        card_title = self.font_small.render("TABLA DE RECORD - SALON DE LA FAMA", True, (160, 220, 255))
        surface.blit(card_title, (self.card_rect.x + 16, self.card_rect.y + 10))

        # Listar los mejores 3 records
        top_scores = self.score_mgr.scores[:3]
        if top_scores:
            for idx, sc in enumerate(top_scores):
                y_pos = self.card_rect.y + 36 + (idx * 26)
                pos_str = f"#{idx + 1}"
                entry_str = f"{pos_str}  Ronda {sc['round']:02d}  -  {sc['player']}  ({sc.get('date', '')})"
                col = (255, 215, 60) if idx == 0 else (200, 225, 255)
                entry_surf = self.font_mono.render(entry_str, True, col)
                surface.blit(entry_surf, (self.card_rect.x + 16, y_pos))
        else:
            no_rec = self.font_small.render("Aun no hay records registrados. ¡Se el primero!", True, (140, 160, 185))
            surface.blit(no_rec, (self.card_rect.x + 16, self.card_rect.y + 45))

    def cleanup(self):
        self.vision.stop()
