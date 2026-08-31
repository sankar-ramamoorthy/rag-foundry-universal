export interface Titled {
  title: string;
}

export interface Named extends Titled {
  name: string;
}

export interface Movable {
  move(): void;
}
