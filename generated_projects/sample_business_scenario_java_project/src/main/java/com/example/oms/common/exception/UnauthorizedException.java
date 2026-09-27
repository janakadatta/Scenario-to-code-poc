package com.example.oms.common.exception;

/**
 * Exception thrown when a user attempts to access or modify a resource they do not own.
 */
public class UnauthorizedException extends DomainException {
    public UnauthorizedException(String message) {
        super("UNAUTHORIZED_ACCESS", message);
    }
}