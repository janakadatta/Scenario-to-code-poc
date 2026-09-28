package com.pension;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@SpringBootApplication
@EnableMongoAuditing
public class PensionApplication {

    public static void main(String[] args) {
        SpringApplication.run(PensionApplication.class, args);
    }
}