package com.example.oms.common.exception;

/**
 * Exception thrown when a requested resource is not found in the database.
 */
public class ResourceNotFoundException extends DomainException {
    public ResourceNotFoundException(String resourceName, String id) {
        super("RESOURCE_NOT_FOUND", String.format("%s with ID '%s' was not found.", resourceName, id));
    }
}