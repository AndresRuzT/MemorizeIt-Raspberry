#include "GridPanel.hpp"
#include <algorithm>

GridPanel::GridPanel() {
    panels.resize(9);
    for (int i = 0; i < 9; ++i) {
        panels[i].index = i;
        panels[i].state = PanelVisualState::IDLE;
        panels[i].stateTimer = 0.0f;
    }
}

void GridPanel::initialize(Rectangle gridArea, float spacing) {
    padding = spacing;
    float cellWidth = (gridArea.width - 2.0f * spacing) / 3.0f;
    float cellHeight = (gridArea.height - 2.0f * spacing) / 3.0f;

    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            int idx = row * 3 + col;
            panels[idx].bounds = {
                gridArea.x + col * (cellWidth + spacing),
                gridArea.y + row * (cellHeight + spacing),
                cellWidth,
                cellHeight
            };
        }
    }
}

void GridPanel::update(float deltaTime) {
    for (auto& p : panels) {
        if (p.stateTimer > 0.0f) {
            p.stateTimer -= deltaTime;
            if (p.stateTimer <= 0.0f) {
                p.stateTimer = 0.0f;
                p.state = PanelVisualState::IDLE;
            }
        }
    }
}

void GridPanel::draw() {
    for (const auto& p : panels) {
        Color baseColor = getColorForState(p.state);
        Color borderColor = getBorderColorForState(p.state);

        // Fondo del panel
        DrawRectangleRounded(p.bounds, 0.18f, 6, baseColor);

        // Borde estilizado estilo consola Among Us
        DrawRectangleRoundedLinesEx(p.bounds, 0.18f, 6, 3.0f, borderColor);

        // Indicador central brillante si está activo
        if (p.state == PanelVisualState::FLASHING || p.state == PanelVisualState::PRESSED) {
            Rectangle inner = {
                p.bounds.x + p.bounds.width * 0.2f,
                p.bounds.y + p.bounds.height * 0.2f,
                p.bounds.width * 0.6f,
                p.bounds.height * 0.6f
            };
            DrawRectangleRounded(inner, 0.25f, 4, Color{ 230, 250, 255, 180 });
        }
    }
}

void GridPanel::setPanelState(int index, PanelVisualState state, float duration) {
    if (index < 0 || index >= static_cast<int>(panels.size())) return;
    panels[index].state = state;
    panels[index].stateTimer = duration;
}

void GridPanel::setAllState(PanelVisualState state, float duration) {
    for (auto& p : panels) {
        p.state = state;
        p.stateTimer = duration;
    }
}

int GridPanel::getPanelAtPosition(Vector2 position) const {
    for (const auto& p : panels) {
        if (CheckCollisionPointRec(position, p.bounds)) {
            return p.index;
        }
    }
    return -1;
}

Rectangle GridPanel::getPanelBounds(int index) const {
    if (index >= 0 && index < static_cast<int>(panels.size())) {
        return panels[index].bounds;
    }
    return { 0, 0, 0, 0 };
}

Color GridPanel::getColorForState(PanelVisualState state) const {
    switch (state) {
        case PanelVisualState::IDLE:
            return Color{ 24, 34, 52, 255 };      // Azul petróleo oscuro
        case PanelVisualState::HOVERED:
            return Color{ 40, 75, 110, 255 };     // Azul medio (iluminado suave)
        case PanelVisualState::FLASHING:
        case PanelVisualState::PRESSED:
            return Color{ 60, 220, 255, 255 };    // Cian eléctrico brillante
        case PanelVisualState::SUCCESS:
            return Color{ 50, 230, 120, 255 };    // Verde éxito
        case PanelVisualState::ERROR:
            return Color{ 235, 45, 60, 255 };     // Rojo error reactor
        default:
            return Color{ 30, 30, 30, 255 };
    }
}

Color GridPanel::getBorderColorForState(PanelVisualState state) const {
    switch (state) {
        case PanelVisualState::IDLE:
            return Color{ 45, 65, 95, 255 };
        case PanelVisualState::HOVERED:
            return Color{ 70, 140, 190, 255 };
        case PanelVisualState::FLASHING:
        case PanelVisualState::PRESSED:
            return Color{ 220, 250, 255, 255 };
        case PanelVisualState::SUCCESS:
            return Color{ 140, 255, 180, 255 };
        case PanelVisualState::ERROR:
            return Color{ 255, 120, 130, 255 };
        default:
            return Color{ 80, 80, 80, 255 };
    }
}
