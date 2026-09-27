package com.example.oms.common.dto;

/**
 * Top-level wrapper for error payloads to maintain uniform JSON error shapes.
 */
public record ErrorResponse(
        ErrorDetails error
) {
    public static ErrorResponse of(String code, String message) {
        return new ErrorResponse(new ErrorDetails(code, message));
    }

    public static ErrorResponse of(String code, String message, java.util.List<String> details) {
        return new ErrorResponse(new ErrorDetails(code, message, details));
    }
}