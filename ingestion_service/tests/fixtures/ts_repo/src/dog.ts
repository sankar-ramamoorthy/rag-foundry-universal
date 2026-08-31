import { Animal } from "./animal";
import { Movable } from "./movable";

export class Dog extends Animal implements Movable {
  move() {
    this.speak();
  }
}
