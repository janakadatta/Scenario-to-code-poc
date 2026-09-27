package com.example.oms.common.exception;

/**
 * Exception thrown when an invalid state transition is requested on an order.
 */
public class InvalidStateTransitionException extends DomainException {
    public InvalidStateTransitionException(String currentState, String targetState) {
        super("INVALID_STATE_TRANSITION",
                String.format("Cannot transition order status from '%s' to '%s'.", currentState, targetState));
    }
}