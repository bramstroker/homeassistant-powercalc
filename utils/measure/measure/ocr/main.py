import argparse

import ocr


def main() -> None:
    """
    Handles command line arguments and begins the real-time OCR by calling ocr_stream().
    A path to the Tesseract cmd root is required.
    """
    parser = argparse.ArgumentParser()

    required_named = parser.add_argument_group("required named arguments")

    required_named.add_argument(
        "-t",
        "--tess_path",
        help="path to the cmd root of tesseract install (see docs for further help)",
        metavar="",
        required=True,
    )
    parser.add_argument(
        "-s",
        "--src",
        help="SRC video source for video capture",
        default=0,
        type=str,
    )

    args = parser.parse_args()

    ocr.tesseract_location(args.tess_path)
    ocr.ocr_stream(source=args.src)


if __name__ == "__main__":
    main()  # '/usr/local/Cellar/tesseract/4.1.1/bin/tesseract'
