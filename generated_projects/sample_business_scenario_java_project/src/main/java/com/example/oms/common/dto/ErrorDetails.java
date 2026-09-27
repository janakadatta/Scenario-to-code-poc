package com.example.oms.common.dto;

import java.time.Instant;
import java.util.List;

/**
 * Standard error response structure as required by backend coding standards.
 * Shape: {"error": {"code": "...", "message": "...", "timestamp": "...", "details": [...]}}
 */
public record ErrorDetails(
        String code,
        String message,
        Instant timestamp,
        List<String> details
) {
    public ErrorDetails(String code, String message, List<String> details) {
        this(code, message, Instant.now(), details);
    }

    public ErrorDetails(String code, String message) {
        this(code, message, Instant.now(), List.of());
    }
}