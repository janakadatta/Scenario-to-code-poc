package com.pension.common.exception;

import com.pension.common.dto.ErrorResponseBody;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponseBody> handleNotFound(ResourceNotFoundException ex) {
        log.warn("Resource not found: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ErrorResponseBody.of("RESOURCE_NOT_FOUND", ex.getMessage()));
    }

    @ExceptionHandler(BusinessValidationException.class)
    public ResponseEntity<ErrorResponseBody> handleBusinessValidation(BusinessValidationException ex) {
        log.warn("Business validation error: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(ErrorResponseBody.of("BUSINESS_VALIDATION_ERROR", ex.getMessage()));
    }

    @ExceptionHandler(DuplicateResourceException.class)
    public ResponseEntity<ErrorResponseBody> handleDuplicate(DuplicateResourceException ex) {
        log.warn("Duplicate resource conflict: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ErrorResponseBody.of("DUPLICATE_RESOURCE", ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponseBody> handleValidationException(MethodArgumentNotValidException ex) {
        List<String> errors = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .toList();
        log.warn("Input validation failed: {}", errors);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ErrorResponseBody.of("INVALID_INPUT", "Validation failed for request parameters", errors));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ErrorResponseBody> handleAccessDenied(AccessDeniedException ex) {
        log.warn("Access denied: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(ErrorResponseBody.of("ACCESS_DENIED", "Access is denied for this resource"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponseBody> handleGenericException(Exception ex) {
        log.error("Unhandled unexpected exception", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponseBody.of("INTERNAL_SERVER_ERROR", "An unexpected internal error occurred"));
    }
}