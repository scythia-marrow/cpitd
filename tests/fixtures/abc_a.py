from abc import ABC, abstractmethod


class Animal(ABC):
    @abstractmethod
    def speak(self):
        """Produce a sound characteristic of the animal."""
        raise NotImplementedError

    @abstractmethod
    def move(self):
        """Perform the primary locomotion action."""
        raise NotImplementedError

    @abstractmethod
    def eat(self, food):
        """Consume the given food item."""
        raise NotImplementedError

    @abstractmethod
    def sleep(self, hours):
        """Sleep for the given number of hours."""
        raise NotImplementedError

    @abstractmethod
    def reproduce(self):
        """Create offspring according to species behavior."""
        raise NotImplementedError

    def breathe(self):
        return "breathing"
