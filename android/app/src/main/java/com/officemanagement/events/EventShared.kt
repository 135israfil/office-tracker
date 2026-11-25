package com.officemanagement.events

import com.officemanagement.ui.components.BadgeTone

// Mirrors frontend/src/views/EventsView.vue / EventDetailView.vue's BOOKING_STATUSES /
// BOOKING_STATUS_LABEL / BOOKING_STATUS_BADGE — kept in one place so the list and the
// detail screen can never show a different label or colour for the same status.
val BOOKING_STATUSES = listOf("ON_COMMUNICATION", "LOCKED", "DONE")

fun bookingStatusLabel(status: String): String = when (status) {
    "ON_COMMUNICATION" -> "On communication"
    "LOCKED" -> "Locked"
    "DONE" -> "Done"
    else -> status
}

fun bookingStatusTone(status: String): BadgeTone = when (status) {
    "DONE" -> BadgeTone.OK
    "LOCKED" -> BadgeTone.DANGER
    else -> BadgeTone.WARN
}

// Mirrors EventDetailView.vue's DOCUMENT_STATUSES/DOCUMENT_STATUS_LABEL.
val DOCUMENT_STATUSES = listOf(
    "VERBAL_COMMUNICATION",
    "PROPOSAL_SENT",
    "WORK_ORDER",
    "VERBAL_CONFIRMATION",
    "INVOICE_SENT",
)

fun documentStatusLabel(status: String): String = when (status) {
    "VERBAL_COMMUNICATION" -> "Verbal communication"
    "PROPOSAL_SENT" -> "Proposal sent"
    "WORK_ORDER" -> "Work order"
    "VERBAL_CONFIRMATION" -> "Verbal confirmation"
    "INVOICE_SENT" -> "Invoice sent"
    else -> status
}

// Mirrors EventDetailView.vue's FINANCIAL_STATUSES/FINANCIAL_STATUS_LABEL.
val FINANCIAL_STATUSES = listOf("ADVANCE", "PARTIAL_PAID", "FULL_PAID")

fun financialStatusLabel(status: String): String = when (status) {
    "ADVANCE" -> "Advance"
    "PARTIAL_PAID" -> "Partial paid"
    "FULL_PAID" -> "Full paid"
    else -> status
}
