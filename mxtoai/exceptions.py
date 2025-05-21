class UnspportedHandleException(Exception):
    def __init__(self, message):
        super().__init__(message)

class HandleAlreadyExistsException(Exception):
    def __init__(self, message):
        super().__init__(message)

class EnvironmentVariableNotFoundException(Exception):
    def __init__(self, message):
        super().__init__(message)
