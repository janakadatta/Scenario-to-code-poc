package com.example.oms.common.exception;

/**
 * Exception thrown when a resource with a unique attribute (e.g. email) already exists.
 */
public class DuplicateResourceException extends DomainException {
    public DuplicateResourceException(String field, String value) {
        super("DUPLICATE_RESOURCE", String.format("A resource with %s '%s' already exists.", field, value));
    }
}