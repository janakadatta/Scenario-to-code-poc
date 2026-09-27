package com.example.oms.common.exception;

/**
 * Exception thrown when stock quantity is insufficient to fulfill an order item request.
 */
public class InsufficientStockException extends DomainException {
    public InsufficientStockException(String productName, int requested, int available) {
        super("INSUFFICIENT_STOCK",
                String.format("Product '%s' has insufficient stock. Requested: %d, Available: %d.", productName, requested, available));
    }
}