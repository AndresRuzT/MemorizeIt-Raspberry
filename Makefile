CXX ?= g++
CXXFLAGS ?= -std=c++17 -O3 -Wall -Wextra -pthread -Iinclude

# Detección de flags para OpenCV y Raylib
OPENCV_CFLAGS ?= $(shell pkg-config --cflags opencv4 2>/dev/null || pkg-config --cflags opencv 2>/dev/null || echo "-I/usr/include/opencv4")
OPENCV_LIBS   ?= $(shell pkg-config --libs opencv4 2>/dev/null || pkg-config --libs opencv 2>/dev/null || echo "-lopencv_core -lopencv_videoio -lopencv_imgproc -lopencv_highgui")

RAYLIB_CFLAGS ?= $(shell pkg-config --cflags raylib 2>/dev/null || echo "")
RAYLIB_LIBS   ?= $(shell pkg-config --libs raylib 2>/dev/null || echo "-lraylib -lGL -lm -lpthread -ldl -lrt -lX11")

ALL_CXXFLAGS = $(CXXFLAGS) $(OPENCV_CFLAGS) $(RAYLIB_CFLAGS)
ALL_LIBS     = $(RAYLIB_LIBS) $(OPENCV_LIBS) -lpthread -lm

SRC_DIR = src
OBJ_DIR = obj
BIN_DIR = bin

SRCS = $(wildcard $(SRC_DIR)/*.cpp)
OBJS = $(patsubst $(SRC_DIR)/%.cpp, $(OBJ_DIR)/%.o, $(SRCS))
TARGET = $(BIN_DIR)/memorizeit

.PHONY: all clean run setup_dirs

all: setup_dirs $(TARGET)

setup_dirs:
	@mkdir -p $(OBJ_DIR) $(BIN_DIR)

$(TARGET): $(OBJS)
	$(CXX) $(OBJS) -o $@ $(ALL_LIBS)
	@echo "Construcción exitosa: $@"

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	$(CXX) $(ALL_CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR) $(BIN_DIR)
	@echo "Limpieza completada."

run: all
	./$(TARGET)
