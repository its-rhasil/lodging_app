"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  checkIn,
  previewCheckIn,
} from "@/services/stay.service";

interface CheckInModalProps {
  roomId: number;
  roomNumber: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function CheckInModal({
  roomId,
  roomNumber,
  onClose,
  onSuccess,
}: CheckInModalProps) {
  const [occupancy, setOccupancy] = useState("1");

  const [roomTypeName, setRoomTypeName] = useState("");
  const [suggestedPrice, setSuggestedPrice] = useState<string | null>(null);
  const [agreedPrice, setAgreedPrice] = useState("");

  const [guestFullName, setGuestFullName] = useState("");
  const [guestPhone, setGuestPhone] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [guestAddress, setGuestAddress] = useState("");

  const [stayHours, setStayHours] = useState("24");

  const [checkInNow, setCheckInNow] = useState(true);
  const [checkInDate, setCheckInDate] = useState("");
  const [checkInTime, setCheckInTime] = useState("");

  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  /*
   * Load pricing whenever occupancy changes.
   */
  useEffect(() => {
    async function loadPreview() {
      const parsedOccupancy = Number(occupancy);

      if (!parsedOccupancy || parsedOccupancy <= 0) {
        setSuggestedPrice(null);
        setAgreedPrice("");
        return;
      }

      setPreviewLoading(true);
      setError("");

      try {
        const preview = await previewCheckIn(
          roomId,
          parsedOccupancy
        );

        setRoomTypeName(preview.room_type_name);
        setSuggestedPrice(preview.suggested_price);

        if (preview.suggested_price !== null) {
          setAgreedPrice(preview.suggested_price);
        } else {
          setAgreedPrice("");
        }
      } catch (error) {
        console.error(
          "Failed to load check-in preview:",
          error
        );

        setSuggestedPrice(null);
        setAgreedPrice("");

        setError(
          error instanceof Error
            ? error.message
            : "Failed to load room pricing"
        );
      } finally {
        setPreviewLoading(false);
      }
    }

    loadPreview();
  }, [roomId, occupancy]);

  /*
   * Submit check-in.
   */
  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setError("");

    const parsedOccupancy = Number(occupancy);
    const parsedStayHours = Number(stayHours);

    if (!parsedOccupancy || parsedOccupancy <= 0) {
      setError("Occupancy must be greater than zero.");
      return;
    }

    if (!parsedStayHours || parsedStayHours <= 0) {
      setError("Stay duration must be greater than zero.");
      return;
    }

    if (!agreedPrice || Number(agreedPrice) <= 0) {
      setError("Agreed price must be greater than zero.");
      return;
    }

    let actualCheckInAt: string | undefined;

    /*
     * If "Check in now" is selected,
     * we don't send actual_check_in_at.
     *
     * The backend will automatically use the current time.
     */
    if (!checkInNow) {
      if (!checkInDate || !checkInTime) {
        setError("Please select both date and time.");
        return;
      }

      const localDateTime = new Date(
        `${checkInDate}T${checkInTime}`
      );

      if (Number.isNaN(localDateTime.getTime())) {
        setError("Invalid check-in date or time.");
        return;
      }

      if (localDateTime > new Date()) {
        setError("Check-in time cannot be in the future.");
        return;
      }

      actualCheckInAt = localDateTime.toISOString();
    }

    setSubmitting(true);

    try {
      await checkIn({
        room_id: roomId,
        guest_full_name: guestFullName,
        guest_phone: guestPhone,
        guest_email: guestEmail || null,
        guest_address: guestAddress || null,
        occupancy: parsedOccupancy,
        stay_hours: parsedStayHours,
        agreed_price: agreedPrice,
        actual_check_in_at: actualCheckInAt,
      });

      onSuccess();
    } catch (error) {
      console.error("Check-in failed:", error);

      setError(
        error instanceof Error
          ? error.message
          : "Check-in failed"
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {/* Background overlay */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
      />

      {/* Center modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-800 dark:bg-gray-900"
          onClick={(event) => event.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Check-in
              </p>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Room {roomNumber}
              </h2>

              {roomTypeName && (
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  {roomTypeName}
                </p>
              )}
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white"
            >
              ✕
            </button>
          </div>

          <form
            onSubmit={handleSubmit}
            className="mt-6 space-y-5"
          >
            {/* Occupancy */}
            <div>
              <label
                htmlFor="occupancy"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Occupancy
              </label>

              <input
                id="occupancy"
                type="number"
                min="1"
                value={occupancy}
                onChange={(event) =>
                  setOccupancy(event.target.value)
                }
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-black outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:focus:border-white dark:focus:ring-white"
              />
            </div>

            {/* Guest name */}
            <div>
              <label
                htmlFor="guestFullName"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Guest name
              </label>

              <input
                id="guestFullName"
                type="text"
                value={guestFullName}
                onChange={(event) =>
                  setGuestFullName(event.target.value)
                }
                placeholder="Enter guest name"
                required
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-black placeholder:text-gray-400 outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500 dark:focus:border-white dark:focus:ring-white"
              />
            </div>

            {/* Phone */}
            <div>
              <label
                htmlFor="guestPhone"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Phone
              </label>

              <input
                id="guestPhone"
                type="tel"
                value={guestPhone}
                onChange={(event) =>
                  setGuestPhone(event.target.value)
                }
                placeholder="Enter phone number"
                required
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-black placeholder:text-gray-400 outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500 dark:focus:border-white dark:focus:ring-white"
              />
            </div>

            {/* Email */}
            <div>
              <label
                htmlFor="guestEmail"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Email
              </label>

              <input
                id="guestEmail"
                type="email"
                value={guestEmail}
                onChange={(event) =>
                  setGuestEmail(event.target.value)
                }
                placeholder="Enter email (optional)"
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-black placeholder:text-gray-400 outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500 dark:focus:border-white dark:focus:ring-white"
              />
            </div>

            {/* Address */}
            <div>
              <label
                htmlFor="guestAddress"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Address
              </label>

              <textarea
                id="guestAddress"
                value={guestAddress}
                onChange={(event) =>
                  setGuestAddress(event.target.value)
                }
                placeholder="Enter address (optional)"
                rows={3}
                className="w-full resize-none rounded-lg border border-gray-300 bg-white px-4 py-3 text-black placeholder:text-gray-400 outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500 dark:focus:border-white dark:focus:ring-white"
              />
            </div>

            {/* Stay duration */}
            <div>
              <label
                htmlFor="stayHours"
                className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Stay duration
              </label>

              <div className="relative">
                <input
                  id="stayHours"
                  type="number"
                  min="1"
                  value={stayHours}
                  onChange={(event) =>
                    setStayHours(event.target.value)
                  }
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 pr-16 text-black outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:focus:border-white dark:focus:ring-white"
                />

                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm text-gray-500 dark:text-gray-400">
                  hours
                </span>
              </div>
            </div>

            {/* Check-in time */}
            <div>
              <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                Check-in time
              </p>

              <div className="space-y-3">
                {/* Check in now */}
                <label className="flex cursor-pointer items-center gap-3">
                  <input
                    type="radio"
                    name="checkInTime"
                    checked={checkInNow}
                    onChange={() => setCheckInNow(true)}
                    className="h-4 w-4"
                  />

                  <span className="text-sm text-gray-900 dark:text-white">
                    Check in now
                  </span>
                </label>

                {/* Custom date/time */}
                <label className="flex cursor-pointer items-center gap-3">
                  <input
                    type="radio"
                    name="checkInTime"
                    checked={!checkInNow}
                    onChange={() => setCheckInNow(false)}
                    className="h-4 w-4"
                  />

                  <span className="text-sm text-gray-900 dark:text-white">
                    Set date & time
                  </span>
                </label>

                {!checkInNow && (
                  <div className="grid grid-cols-2 gap-3 pl-7">
                    <div>
                      <label
                        htmlFor="checkInDate"
                        className="mb-1.5 block text-xs text-gray-500 dark:text-gray-400"
                      >
                        Date
                      </label>

                      <input
                        id="checkInDate"
                        type="date"
                        value={checkInDate}
                        onChange={(event) =>
                          setCheckInDate(event.target.value)
                        }
                        max={
                          new Date()
                            .toISOString()
                            .split("T")[0]
                        }
                        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-black outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:focus:border-white dark:focus:ring-white"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="checkInTime"
                        className="mb-1.5 block text-xs text-gray-500 dark:text-gray-400"
                      >
                        Time
                      </label>

                      <input
                        id="checkInTime"
                        type="time"
                        value={checkInTime}
                        onChange={(event) =>
                          setCheckInTime(event.target.value)
                        }
                        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-black outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:focus:border-white dark:focus:ring-white"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Pricing */}
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Pricing
              </p>

              <div className="mt-3 space-y-4">
                {/* Suggested price */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Suggested price
                  </span>

                  <span className="font-medium text-gray-900 dark:text-white">
                    {previewLoading
                      ? "Loading..."
                      : suggestedPrice !== null
                        ? `₹${Number(suggestedPrice)}`
                        : "Not available"}
                  </span>
                </div>

                {/* Agreed price */}
                <div>
                  <label
                    htmlFor="agreedPrice"
                    className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    Agreed price
                  </label>

                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400">
                      ₹
                    </span>

                    <input
                      id="agreedPrice"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={agreedPrice}
                      onChange={(event) =>
                        setAgreedPrice(event.target.value)
                      }
                      required
                      className="w-full rounded-lg border border-gray-300 bg-white py-3 pl-8 pr-4 text-black outline-none focus:border-gray-900 focus:ring-1 focus:ring-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:focus:border-white dark:focus:ring-white"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              <button
                type="submit"
                disabled={submitting || previewLoading}
                className="rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
              >
                {submitting ? "Checking in..." : "Check in"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}