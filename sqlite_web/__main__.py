import sys

if sys.version_info[0] == 2:
    from sqlite_web import main
else:
    from .sqlite_web import main


if __name__ == '__main__':
    main()

