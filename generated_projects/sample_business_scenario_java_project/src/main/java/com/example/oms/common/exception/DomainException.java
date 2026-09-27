package com.example.oms.common.exception;

import lombok.Getter;

/**
 * Base abstract exception class for domain business errors.
 */
@Getter
public abstract class DomainException extends RuntimeException {
    private final String errorCode;

    protected DomainException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }
}