package com.acme;

import com.acme.util.Util;
import com.acme.other.*;

public class Animal implements Movable {
    private String name;

    public Animal(String name) {
        this.name = name;
    }

    public String speak() {
        return name;
    }

    public String describe() {
        return speak();
    }

    @Override
    public void moveTo(int x, int y) {
        speak();
    }

    public int scaled(int x) {
        return Util.calc(x);
    }

    public void overload(int x) {
    }

    public void overload(String x) {
    }

    public class Tag {
        public void tagMethod() {
        }
    }
}
