import dnf

try:
    from dnfpluginscore import ArgumentParser
except ImportError:
    import argparse

    class ArgumentParser(argparse.ArgumentParser):
        """Parses the argument and options given to a tool from DNF.

        default help commands (-h, --help) is disabled and a custom --help-cmd
        is add by default
        Errors in parse of option/arguments will print the help and raise
        a dnf.exception.Error
        """

        def __init__(self, cmd, **kwargs):
            argparse.ArgumentParser.__init__(self, prog='dnf %s' % cmd,
                                             add_help=False, **kwargs)
            self.add_argument('--help-cmd', action='store_true',
                              help='show this help about this tool')

        def error(self, message):
            """Overload the default error method.

            We dont wan't the default exit action on parse
            errors, just raise an AttributeError we can catch.
            """
            raise AttributeError(message)

        def parse_args(self, args=None, namespace=None):
            try:
                opts = argparse.ArgumentParser.parse_args(self, args)
            except AttributeError as e:
                self.print_help()
                raise dnf.exceptions.Error(str(e))
            return opts
