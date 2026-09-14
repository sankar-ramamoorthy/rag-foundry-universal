pub struct Circle {
    radius: f64,
}

impl Circle {
    pub fn new(radius: f64) -> Self {
        Circle { radius }
    }

    pub fn area(&self) -> f64 {
        self.radius_squared()
    }

    fn radius_squared(&self) -> f64 {
        self.radius * self.radius
    }
}
