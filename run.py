from paradox import main
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", type=str, default=None,
                    help="specify path to an alternative configuration file")

args = parser.parse_args()

main.main(args)
