# MemorizeIt User Guide

Welcome to MemorizeIt, an interactive touchless memory game designed for Raspberry Pi 4 and modern computers equipped with a webcam. This guide walks you through setting up your play area, understanding the gesture mechanics, and mastering every round of the game.

## Getting Started Quickly

Before launching the game, connect your USB webcam or camera module to your computer and plug in your audio speakers or headphones.

You can launch the game using the included startup script:

```bash
./run.sh
```

If you wish to specify which camera to use when multiple video devices are connected, run the Python entry script directly:

```bash
python3 main.py --cam 0
```

To exit the game at any moment, simply press the Escape key.

## Creating the Ideal Play Space

Because MemorizeIt relies on computer vision to track your hand gestures, proper lighting and camera placement ensure the smoothest possible experience.

* **Camera Placement:** Position your camera directly in front of you at roughly chest level. A comfortable distance between your hand and the camera lens is between 50 and 90 centimeters.
* **Lighting:** Ensure your face and hands receive even, natural light from the front or above. Avoid bright lamps or sunny windows directly behind you, as strong backlighting creates dark silhouettes that make tracking harder.
* **Background:** A simple, uncluttered background allows the vision engine to cleanly isolate your hand geometry.

## Natural Hand Posture and Tracking

MemorizeIt uses an intelligent posture verification system to guarantee that intentional gestures trigger game actions rather than casual hand movements.

* **The Pointing Gesture:** Extend your index finger forward clearly toward the screen, while keeping your thumb, middle finger, ring finger, and pinky gently curled toward your palm.
* **Camera Mirroring:** The camera window on the right side of the screen is mirrored horizontally. When you move your hand to your right, the green tracking dot on the screen moves right naturally, matching your intuition.
* **Smooth Pointer Feedback:** A bright green dot shows the exact position of your fingertip in real time. The movement is filtered by an adaptive low pass algorithm that eliminates jitter while keeping response times immediate.

## Step by Step Gameplay

### 1. Activating Standby Mode (5 Second Dwell)

When the game launches, it sits in a peaceful standby state waiting for a player.

Look at the camera window on the right side of the screen. You will notice a glowing circular zone in the center.

Bring your extended index finger into this central circle and hold it steady. A circular progress ring will begin filling up while an audible countdown tone plays each second. Keep your finger inside the ring for 5 continuous seconds to wake up the reactor and start your session.

If you are setting up or testing your camera and want to skip the 5 second gesture countdown, simply press Space or Enter on your keyboard to start immediately.

### 2. Watching and Listening to the Sequence

Once active, the game enters the demonstration phase.

The 3x3 grid on the left displays a randomized sequence of illuminated tiles. Each tile flashes with vibrant cyan energy and emits its own unique synthesized musical tone between C4 and D5.

Watch the pattern closely and listen to the melodic rhythm. The game plays one step per beat, giving you clear visual and audio cues for each position.

### 3. Your Turn to Play (2.0 Second Dwell)

As soon as the demonstration finishes, the board turns receptive and awaits your response.

Guide your green pointer over the first tile from the pattern you memorized. As your pointer hovers over the tile, an energy meter starts filling around the panel border.

Hold your position over the tile for 2.0 continuous seconds to fully charge the energy gauge. When full, the tile acknowledges your selection with a confirmation flash and tone.

Repeat this process for each subsequent tile in the correct chronological order.

The tracking engine includes a generous 0.20 second forgiveness buffer. If your hand moves slightly out of the panel boundary due to a quick tremor, the charge does not immediately reset, giving you time to stay centered.

### 4. Progression and Rounds

Completing the full sequence correctly earns a victorious green shimmer across the board. The game increments your current round counter, adds one new random tile to the sequence, and demonstrates the updated pattern.

The game is infinite. There is no ceiling on rounds, so you can test your memory as far as your focus can take you.

### 5. Game Over and Saving Records

Selecting an incorrect tile immediately locks the reactor. An error alarm sounds, the grid illuminates in crimson red, and the final round score is calculated.

Your score is checked against past performances. If you achieved a personal best, your score becomes the top record. The game writes your result to the high scores file and returns you safely to the standby screen, ready for another attempt.

## Helpful Keyboard Shortcuts

During gameplay, several handy keyboard shortcuts are available:

* **Space or Enter:** Start the game immediately from standby, or restart quickly after a game over.
* **C:** Cycle to the next available video camera device without restarting the game.
* **B:** Recalibrate background lighting baseline and reset filter coordinates.
* **R:** Force an immediate reset back to the initial standby state.
* **Escape:** Close the window and exit the application cleanly.

## Understanding Your Score Ledger

Every finished session is stored locally inside the project directory in a file named highscores.json.

The game tracks:

* **best_round:** The highest round number ever achieved on this installation.
* **best_player:** The name associated with the current record holder.
* **scores:** A chronological list of recent game attempts with round numbers and timestamps.

The lower right corner of the game screen displays the top record and your current progress during active play.

## Troubleshooting Common Questions

### The green pointer does not appear or flickers

Check that your index finger is clearly pointing out with your other fingers curled in. If the room is too dark, increase front lighting so the camera can clearly see your finger contours. You can also press the B key to recalibrate the tracker.

### The camera preview is showing the wrong video device

Press the C key on your keyboard to cycle through connected cameras until the correct feed appears on screen. Alternatively, start the program with the specific camera index using `python3 main.py --cam 0` or `python3 main.py --cam 1`.

### The audio tones are not playing

Ensure your audio output device is connected and unmuted in your operating system. MemorizeIt synthesizes sound procedurally using the Pygame mixer, which works out of the box with standard ALSA, PulseAudio, and PipeWire sound servers.
