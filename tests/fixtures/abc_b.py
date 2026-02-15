from abc import ABC, abstractmethod


class Vehicle(ABC):
    @abstractmethod
    def speak(self):
        """Produce a sound characteristic of the vehicle."""
        raise NotImplementedError

    @abstractmethod
    def move(self):
        """Perform the primary locomotion action."""
        raise NotImplementedError

    @abstractmethod
    def eat(self, food):
        """Consume the given fuel item."""
        raise NotImplementedError

    @abstractmethod
    def sleep(self, hours):
        """Idle for the given number of hours."""
        raise NotImplementedError

    @abstractmethod
    def reproduce(self):
        """Manufacture a copy according to factory behavior."""
        raise NotImplementedError

    def refuel(self):
        return "refueling"
