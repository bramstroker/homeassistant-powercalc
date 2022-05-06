import argparse

import ocr


def main():
    """
    Handles command line arguments and begins the real-time OCR by calling ocr_stream().
    A path to the Tesseract cmd root is required, but all other params are optional.

    Example command-line use: python3 Main.py -t /usr/local/Cellar/tesseract/4.1.1/bin/tesseract

    optional arguments:
      -h, --help         show this help message and exit
      -c  , --crop       crop OCR area in pixels (two vals required): width height
      -v , --view_mode   view mode for OCR boxes display (default=1)
      -sv, --show_views  show the available view modes and descriptions
      -l , --language    code for tesseract language, use + to add multiple (ex: chi_sim+chi_tra)
      -sl, --show_langs  show list of tesseract (4.0+) supported langs

    required named arguments:
      -t , --tess_path   path to the cmd root of tesseract install (see docs for further help)
    """
    parser = argparse.ArgumentParser()

    # Required:
    requiredNamed = parser.add_argument_group('required named arguments')

    requiredNamed.add_argument('-t', '--tess_path',
                               help="path to the cmd root of tesseract install (see docs for further help)",
                               metavar='', required=True)
    parser.add_argument("-s", "--src", help="SRC video source for video capture",
                        default=0, type=int)

    args = parser.parse_args()

    ocr.tesseract_location(args.tess_path)
    ocr.ocr_stream(source=args.src)


if __name__ == '__main__':
    main()  # '/usr/local/Cellar/tesseract/4.1.1/bin/tesseract'