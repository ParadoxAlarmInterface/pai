from abc import abstractmethod

from construct import Container


class ConnectionHandler:
    @abstractmethod
    def on_message(self, raw: bytes):
        """
        Connection protocol will call this method when a serial pass through payload be received
        :param raw: bytes
        :return:
        """

    @abstractmethod
    def on_connection(self):
        """
        Connection protocol will call this method when a connection is established
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def on_connection_loss(self):
        """
        Connection protocol will call this method when a connection was lost.
        :return:
        """
        raise NotImplementedError()


class IPConnectionHandler(ConnectionHandler):
    @abstractmethod
    def on_ip_message(self, container: Container):
        """
        Connection protocol will call this method upon receiving an ip150 message that is not a serial pass through.
        Will not be used with IP Bare and Serial connections.
        :param container: IPMessageResponse parse result
        :return:
        """
