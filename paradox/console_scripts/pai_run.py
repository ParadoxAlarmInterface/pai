import paradox.main
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default=None,
                        help="specify path to an alternative configuration file")

    args = parser.parse_args()

    paradox.main.main(args)

if __name__ == '__main__':
    main()