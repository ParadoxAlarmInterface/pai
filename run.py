from paradox.lib import help

try:
	from paradox.console_scripts.pai_run import main
except ImportError as error:
    help.import_error_help(error)

if __name__ == '__main__':
    main()
    
