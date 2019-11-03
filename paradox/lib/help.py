import logging
logger = logging.getLogger('PAI').getChild(__name__)

MODULES = {
    'construct': dict(mandatory=True, desc='basic operation', install_name='construct>=2.9.43'),
    'argparse': dict(mandatory=True, desc='basic operation', install_name='argparse>=1.4.0'),
    'pubsub': dict(mandatory=True, desc='basic operation', install_name='PyPubSub=>4.0.3'),
    'pyserial': dict(mandatory=False, desc='the serial connection', install_name='pyserial>=3.4'),
    'serial_asyncio': dict(mandatory=False, desc='the serial connection', install_name='pyserial-asyncio>=0.4'),
    'pushbullet': dict(mandatory=False, desc='the Pushbullet interface', install_name='pushbullet.py=>0.11.0'),
    'requests': dict(mandatory=False, desc='the IP150 connection', install_name='requests>=2.20.0'),
    'ws4py': dict(mandatory=False, desc='the Pushbullet interface', install_name='ws4py>=0.4.2'),
    'yaml': dict(mandatory=False, desc='the IP150 connection', install_name='yaml'),
    'chump': dict(mandatory=False, desc='the Pushover interface', install_name='chump>=1.6.0'),
    'pydbus': dict(mandatory=False, desc='the Signal interface', install_name='pydbus>=0.6.0'),
    'gi': dict(mandatory=False, desc='the Signal interface', install_name='gi>=1.2'),
}

def import_error_help(error):
    logger.error("Could not import Python3 module '{}': {}\n".format(error.name, error))

    if error.name in MODULES:
        m = MODULES[error.name]
        logger.error("The module is required for {} and IS{} mandatory.".format(m['desc'], ' NOT' if not m['mandatory'] else ''))
        if  not m['mandatory']:
            logger.error('If you do not require such functionality, you can disable it in the config file,')
            logger.error('and skip installing the module.\n')
        logger.error("To install ONLY this module, execute: \n")
        logger.error(" pip3 install '{}'\n".format(m['install_name']))
    
    logger.error("To install ALL modules required, go to the main project folder and execute:\n")
    logger.error(" pip3 -r requirements.txt\n")
    logger.error("Take in consideration that the 'requirements.txt' file only has the most common modules enabled.")
    logger.error("Uncomment the entries as required for your setup.")
    logger.error("ATTENTION: If this module is not listed there, please report the bug.")
    import sys
    
    sys.exit(-1)

