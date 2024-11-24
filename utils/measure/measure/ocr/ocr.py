from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime
from decimal import Decimal, DecimalException
from pathlib import Path
from threading import Thread

import cv2
import numpy as np
import pytesseract

logging.basicConfig(
    level=logging.getLevelName("DEBUG"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(sys.path[0], "ocr.log")),
        logging.StreamHandler(),
    ],
)

_LOGGER = logging.getLogger("ocr")

WINDOW_NAME = "Realtime OCR"

OCR_SLEEP = 0.5


def tesseract_location(root: str) -> None:
    """
    Sets the tesseract cmd root and exits is the root is not set correctly

    Tesseract needs a pointer to exec program included in the install.
    Example: User/Documents/tesseract/4.1.1/bin/tesseract
    See tesseract documentation for help.
    """
    try:
        pytesseract.pytesseract.tesseract_cmd = root
    except FileNotFoundError:
        print(
            "Please double check the Tesseract file directory or ensure it's installed.",
        )
        sys.exit(1)


class RateCounter:
    """
    Class for finding the iterations/second of a process

    `Attributes:`
        start_time: indicates when the time.perf_counter() began
        iterations: determines number of iterations in the process

    `Methods:`
        start(): Starts a time.perf_counter() and sets it in the self.start_time attribute
        increment(): Increases the self.iterations attribute
        rate(): Returns the iterations/seconds
    """

    def __init__(self) -> None:
        self.start_time = None
        self.iterations: int = 0

    def start(self) -> RateCounter:
        """
        Starts a time.perf_counter() and sets it in the self.start_time attribute

        :return: self
        """
        self.start_time = time.perf_counter()
        return self

    def increment(self) -> None:
        """
        Increases the self.iterations attribute
        """
        self.iterations += 1

    def rate(self) -> float:
        """
        Returns the iterations/seconds
        """
        elapsed_time = time.perf_counter() - self.start_time
        return self.iterations / elapsed_time

    def render(self, frame: np.ndarray, rate: float) -> np.ndarray:
        """
        Places text showing the iterations per second in the CV2 display loop.

        This is for demonstrating the effects of multi-threading.

        :param frame: CV2 display frame for text destination
        :param rate: Iterations per second rate to place on image

        :return: CV2 display frame with rate added
        """

        cv2.putText(
            frame,
            f"{int(rate)} Iterations/Second",
            (10, 35),
            cv2.FONT_HERSHEY_DUPLEX,
            1.0,
            (255, 255, 255),
        )
        return frame


class VideoStream:
    """Class for grabbing frames from CV2 video capture."""

    def __init__(self, src: int | str = 0) -> None:
        self.stream = cv2.VideoCapture(src)
        (self.grabbed, self.frame) = self.stream.read()
        if not self.grabbed or self.frame is None:
            print("Could not find camera")
            exit(1)
        self.stopped = False
        cv2.namedWindow(WINDOW_NAME)

    def start(self) -> VideoStream:
        """
        Creates a thread targeted at get(), which reads frames from CV2 VideoCapture

        :return: self
        """
        Thread(target=self.get, args=()).start()
        return self

    def get(self) -> None:
        """
        Continuously gets frames from CV2 VideoCapture and sets them as self.frame attribute
        """
        while not self.stopped:
            (self.grabbed, self.frame) = self.stream.read()

    def get_video_dimensions(self) -> tuple[int, int]:
        """
        Gets the width and height of the video stream frames

        :return: height `int` and width `int` of VideoCapture
        """
        width = self.stream.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = self.stream.get(cv2.CAP_PROP_FRAME_HEIGHT)
        return int(width), int(height)

    def stop_process(self) -> None:
        """
        Sets the self.stopped attribute as True and kills the VideoCapture stream read
        """
        self.stopped = True

    def capture_image(
        self,
        frame: np.ndarray | None = None,
        captures: int = 0,
    ) -> int:
        """
        Capture a .jpg during CV2 video stream. Saves to a folder /images in working directory.

        :param frame: CV2 frame to save
        :param captures: (optional) Number of existing captures to append to filename

        :return: Updated number of captures. If capture param not used, returns 1 by default
        """
        if frame is None:
            frame = self.frame

        cwd_path = os.getcwd()
        Path(cwd_path + "/images").mkdir(parents=False, exist_ok=True)

        now = datetime.now()
        # Example: "OCR 2021-04-8 at 12:26:21-1.jpg"  ...Handles multiple captures taken in the same second
        name = "OCR " + now.strftime("%Y-%m-%d") + " at " + now.strftime("%H:%M:%S") + "-" + str(captures + 1) + ".jpg"
        path = "images/" + name
        cv2.imwrite(path, frame)
        captures += 1
        print(name)
        return captures


class OcrRegionSelection:
    def __init__(self, video_stream: VideoStream) -> None:
        self.selection = None
        self.drag_start = None
        self.is_selecting = False
        self.stream = video_stream

    def start(self) -> OcrRegionSelection:
        """
        Creates a thread targeted at get(), which reads frames from CV2 VideoCapture

        :return: self
        """
        Thread(target=self.register_mouse_callback, args=()).start()
        return self

    def register_mouse_callback(self) -> None:
        cv2.setMouseCallback(WINDOW_NAME, self.draw_rectangle)

    # Method to track mouse events
    def draw_rectangle(self, event: int, x: int, y: int) -> None:
        x, y = np.int16([x, y])

        if event == cv2.EVENT_LBUTTONDOWN:
            # Start selection
            if not self.is_selecting:
                self.drag_start = (x, y)
                self.is_selecting = True
            # Confirm selection
            else:
                x_start, y_start = self.drag_start
                self.selection = (x_start, y_start, x, y)
                self.is_selecting = False
                self.stream.capture_image(self.get_cropped_frame(self.stream.frame))

        if event == cv2.EVENT_MOUSEMOVE and self.is_selecting and self.drag_start:
            x_start, y_start = self.drag_start
            self.selection = (x_start, y_start, x, y)

    def render(self, frame: np.ndarray) -> np.ndarray:
        if self.selection:
            cv2.rectangle(
                frame,
                (self.selection[0], self.selection[1]),
                (self.selection[2], self.selection[3]),
                (0, 255, 0),
                2,
            )
        else:
            (h, w) = frame.shape[:2]
            y_center = h // 2
            cv2.rectangle(
                frame,
                (100, y_center - 40),
                (1400, y_center + 90),
                (0, 0, 0),
                -1,
            )
            cv2.putText(
                frame,
                "Start drawing the OCR region",
                (100, h // 2),
                cv2.FONT_HERSHEY_DUPLEX,
                1.5,
                (0, 255, 0),
            )
            cv2.putText(
                frame,
                "Click, drag, and click another time to confirm",
                (100, h // 2 + 50),
                cv2.FONT_HERSHEY_DUPLEX,
                1.5,
                (0, 255, 0),
            )
        return frame

    def has_selection(self) -> bool:
        return self.selection is not None

    def get_cropped_frame(self, frame: np.ndarray) -> np.ndarray:
        return frame[
            self.selection[1] : self.selection[3],
            self.selection[0] : self.selection[2],
        ]


class OCR:
    """Class for creating a pytesseract OCR process in a dedicated thread"""

    def __init__(
        self,
        video_stream: VideoStream,
        region_selection: OcrRegionSelection,
    ) -> None:
        self.measurement: Decimal | None = None
        self.stopped: bool = False
        self.region_selection = region_selection
        self.video_stream = video_stream
        self.file = None

    def start(self) -> OCR:
        """
        Creates a thread targeted at the ocr process
        :return: self
        """
        Thread(target=self.do_ocr, args=()).start()
        return self

    def do_ocr(self) -> None:
        """
        Creates a process where frames are continuously grabbed from the exchange and processed by pytesseract OCR.
        """
        while not self.stopped:
            if self.video_stream is not None and self.region_selection.has_selection():
                try:
                    frame = self.video_stream.frame
                    frame = self.region_selection.get_cropped_frame(frame)

                    # Convert to grayscale for easier OCR detection
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

                    match = pytesseract.image_to_string(
                        frame,
                        config="-c tessedit_char_whitelist='0123456789.'",
                    )
                    _LOGGER.debug("OCR match: %s", match.strip())
                    if len(match) > 0:
                        try:
                            measurement = Decimal(match)
                            _LOGGER.info("Measurement: %.2f", measurement)
                        except DecimalException:
                            _LOGGER.error("Cannot convert OCR match to decimal")
                            continue
                        if not self.validate_measurement(measurement):
                            continue
                        self.measurement = measurement
                        self.write_result(self.measurement)
                    time.sleep(OCR_SLEEP)
                except Exception as e:  # noqa: BLE001
                    _LOGGER.error("OCR error: %s", e)

    def write_result(self, measurement: Decimal) -> None:
        if self.file is None:
            file_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "ocr_results.txt",
            )
            self.file = open(file_path, "a")  # noqa: SIM115

        self.file.write(f"{time.time()};{measurement!s}\n")
        self.file.flush()

    def stop_process(self) -> None:
        """
        Sets the self.stopped attribute to True and kills the ocr() process
        """
        self.file.close()
        self.stopped = True

    def render(self, frame: np.ndarray) -> np.ndarray:
        if self.measurement is None:
            return frame
        return cv2.putText(
            frame,
            str(self.measurement),
            (100, 100),
            cv2.FONT_HERSHEY_DUPLEX,
            1.5,
            (0, 255, 0),
        )

    def validate_measurement(self, measurement: Decimal) -> bool:
        if measurement > 100:
            _LOGGER.info("Measurement was too high, discarding")
            return False

        if measurement < 0.05:
            _LOGGER.info("Measurement was too low, discarding")
            return False

        if self.measurement:
            diff_percentage = self.get_percentage_change(self.measurement, measurement)
            _LOGGER.debug("Percentage diff: %d", diff_percentage)
            if diff_percentage > 120:
                _LOGGER.info(
                    "Difference between measurements is too high, this must be wrong",
                )
                return False

        return True

    @staticmethod
    def get_percentage_change(current: Decimal, previous: Decimal) -> int:
        try:
            if current == previous:
                return 0
            if current > previous:
                return int((abs(current - previous) / previous) * 100)
            return int((abs(previous - current) / current) * 100)
        except ZeroDivisionError:
            return 100000


def ocr_stream(source: str = "0") -> None:
    """
    Begins the video stream and text OCR in two threads, then shows the video in a CV2 frame with the OCR
    boxes overlaid in real-time.
    """

    video_stream = VideoStream(
        source,
    ).start()  # Starts reading the video stream in dedicated thread
    region_selection = OcrRegionSelection(video_stream).start()
    ocr = OCR(
        video_stream,
        region_selection,
    ).start()  # Starts optical character recognition in dedicated thread
    cps1 = RateCounter().start()

    print("OCR stream started")
    print(f"Active threads: {threading.active_count()}")

    # Main display loop
    print("\nPUSH q TO VIEW VIDEO STREAM\n")
    while True:
        # Quit condition:
        pressed_key = cv2.waitKey(1) & 0xFF
        if pressed_key == ord("q"):
            video_stream.stop_process()
            ocr.stop_process()
            print("OCR stream stopped\n")
            break

        frame = video_stream.frame

        frame = cps1.render(frame, cps1.rate())
        frame = ocr.render(frame)
        frame = region_selection.render(frame)

        cv2.imshow(WINDOW_NAME, frame)
        cps1.increment()
