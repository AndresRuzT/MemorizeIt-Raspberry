#pragma once

#include "raylib.h"
#include <vector>

enum class PanelVisualState {
    IDLE,
    HOVERED,
    FLASHING,
    PRESSED,
    SUCCESS,
    ERROR
};

struct Panel {
    Rectangle bounds;
    int index;
    PanelVisualState state{PanelVisualState::IDLE};
    float stateTimer{0.0f};
};

class GridPanel {
public:
    GridPanel();

    void initialize(Rectangle gridArea, float spacing = 14.0f);
    void update(float deltaTime);
    void draw();

    void setPanelState(int index, PanelVisualState state, float duration = 0.35f);
    void setAllState(PanelVisualState state, float duration = 0.45f);

    int getPanelAtPosition(Vector2 position) const;
    Rectangle getPanelBounds(int index) const;

private:
    std::vector<Panel> panels;
    float padding{14.0f};

    Color getColorForState(PanelVisualState state) const;
    Color getBorderColorForState(PanelVisualState state) const;
};
