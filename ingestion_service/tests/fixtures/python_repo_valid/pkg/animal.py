from .movable import Movable
from .util.helpers import calc


class Animal(Movable):
    def speak(self):
        return "..."

    def describe(self):
        return self.speak()

    def move_to(self, x, y):
        self.speak()

    def scaled(self, x):
        return calc(x)
