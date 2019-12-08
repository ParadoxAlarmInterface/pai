#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "João Paulo Barraca, Jevgeni Kiski"
__copyright__ = "Copyright 2018-2019, João Paulo Barraca"
__credits__ = ["Tihomir Heidelberg", "Louis Rossouw"]
__license__ = "EPL"
__version__ = "0.1"
__maintainer__ = "João Paulo Barraca"
__email__ = "jpbarraca@gmail.com"
__status__ = "Beta"

from paradox.lib import help

try:
	from paradox.console_scripts.pai_run import main
except ImportError as error:
    help.import_error_help(error)

if __name__ == '__main__':
    main()
    
