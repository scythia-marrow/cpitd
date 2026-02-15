from abc import ABC, abstractmethod


class Vehicle(ABC):
    @abstractmethod
    def speak(self):
        pass

    @abstractmethod
    def move(self):
        pass

    def refuel(self):
        return "refueling"
