

#Base Exception for the GTNH Calculator
class GTNHCalculatorException(Exception):
    pass


class DataLoadingException(GTNHCalculatorException):
    pass


class MissingOutputException(GTNHCalculatorException):
    pass
