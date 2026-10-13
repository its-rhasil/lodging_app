"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createRoom,
  getRooms,
} from "@/services/room.service";
import { getRoomTypeOptions } from "@/services/room-type.service";

export default function RoomsPage() {
  const queryClient = useQueryClient();

  const [showCreateRoom, setShowCreateRoom] = useState(false);

  const {
    data: rooms = [],
    isLoading: roomsLoading,
    isError: roomsError,
  } = useQuery({
    queryKey: ["rooms"],
    queryFn: getRooms,
  });

  const {
    data: roomTypes = [],
    isLoading: roomTypesLoading,
  } = useQuery({
    queryKey: ["room-type-options"],
    queryFn: getRoomTypeOptions,
  });

  const createRoomMutation = useMutation({
    mutationFn: createRoom,

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["rooms"],
      });

      await queryClient.invalidateQueries({
        queryKey: ["dashboard"],
      });

      setShowCreateRoom(false);
    },
  });

  return (
    <main className="min-h-screen bg-[#f7f5ef] px-5 py-5 dark:bg-gray-950">
      <div className="mx-auto max-w-[1400px]">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Rooms
            </h1>

            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Manage rooms in your property
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowCreateRoom(true)}
            className="rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
          >
            + Add Room
          </button>
        </div>

        {/* Loading */}
        {roomsLoading && (
          <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Loading rooms...
            </p>
          </div>
        )}

        {/* Error */}
        {roomsError && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-900/50 dark:bg-red-950/30">
            <p className="text-sm text-red-700 dark:text-red-400">
              Unable to load rooms.
            </p>
          </div>
        )}

        {/* Room list */}
        {!roomsLoading && !roomsError && (
          <div className="mt-6 overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">

            <div className="grid grid-cols-[120px_1fr_160px] border-b border-gray-200 px-5 py-3 text-xs font-medium uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:text-gray-400">
              <span>Room</span>
              <span>Room Type</span>
              <span>Status</span>
            </div>

            {rooms.length === 0 ? (
              <div className="px-5 py-12 text-center">
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  No rooms have been added yet.
                </p>

                <button
                  type="button"
                  onClick={() => setShowCreateRoom(true)}
                  className="mt-3 text-sm font-medium text-gray-900 underline dark:text-white"
                >
                  Add your first room
                </button>
              </div>
            ) : (
              rooms.map((room) => (
                <div
                  key={room.id}
                  className="grid grid-cols-[120px_1fr_160px] items-center border-b border-gray-100 px-5 py-4 last:border-b-0 dark:border-gray-800"
                >
                  <span className="font-medium text-gray-900 dark:text-white">
                    {room.room_number}
                  </span>

                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    {room.room_type_name}
                  </span>

                  <StatusBadge status={room.operational_status} />
                </div>
              ))
            )}
          </div>
        )}

        {/* Create Room Modal */}
        {showCreateRoom && (
          <CreateRoomModal
            roomTypes={roomTypes}
            loading={roomTypesLoading}
            submitting={createRoomMutation.isPending}
            error={
              createRoomMutation.error instanceof Error
                ? createRoomMutation.error.message
                : ""
            }
            onCancel={() => setShowCreateRoom(false)}
            onSubmit={(data) =>
              createRoomMutation.mutateAsync(data)
            }
          />
        )}
      </div>
    </main>
  );
}

function StatusBadge({
  status,
}: {
  status: string;
}) {
  const styles: Record<string, string> = {
    available:
      "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
    cleaning:
      "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-400",
    maintenance:
      "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  };

  return (
    <span
      className={`inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium capitalize ${
        styles[status] ??
        "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
      }`}
    >
      {status}
    </span>
  );
}

function CreateRoomModal({
  roomTypes,
  loading,
  submitting,
  error,
  onCancel,
  onSubmit,
}: {
  roomTypes: {
    id: number;
    name: string;
    capacity: number;
  }[];
  loading: boolean;
  submitting: boolean;
  error: string;
  onCancel: () => void;
  onSubmit: (data: {
    room_type_id: number;
    room_number: number;
  }) => Promise<unknown>;
}) {
  const [roomNumber, setRoomNumber] = useState("");
  const [roomTypeId, setRoomTypeId] = useState("");
  const [formError, setFormError] = useState("");

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setFormError("");

    if (!roomNumber) {
      setFormError("Please enter a room number.");
      return;
    }

    const number = Number(roomNumber);

    if (!Number.isInteger(number) || number <= 0) {
      setFormError("Room number must be a valid positive number.");
      return;
    }

    if (!roomTypeId) {
      setFormError("Please select a room type.");
      return;
    }

    try {
      await onSubmit({
        room_type_id: Number(roomTypeId),
        room_number: number,
      });
    } catch {
      // Keep modal open when request fails.
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]"
        onClick={() => {
          if (!submitting) {
            onCancel();
          }
        }}
      />

      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-800 dark:bg-gray-900"
        >
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Add Room
              </h2>

              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Add a room to your property.
              </p>
            </div>

            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              ✕
            </button>
          </div>

          <div className="mt-6 space-y-4">

            {/* Room Number */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Room Number
              </label>

              <input
                type="text"
                inputMode="numeric"
                value={roomNumber}
                onChange={(event) => {
                  setRoomNumber(
                    event.target.value.replace(/\D/g, "")
                  );
                }}
                placeholder="101"
                disabled={submitting}
                className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-300 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
              />
            </div>

            {/* Room Type */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Room Type
              </label>

              <select
                value={roomTypeId}
                onChange={(event) =>
                  setRoomTypeId(event.target.value)
                }
                disabled={submitting || loading}
                className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-400 focus:ring-1 focus:ring-gray-300 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
              >
                <option value="">
                  {loading
                    ? "Loading room types..."
                    : "Select room type"}
                </option>

                {roomTypes.map((roomType) => (
                  <option
                    key={roomType.id}
                    value={roomType.id}
                  >
                    {roomType.name} · {roomType.capacity}{" "}
                    {roomType.capacity === 1
                      ? "guest"
                      : "guests"}
                  </option>
                ))}
              </select>
            </div>

            {(formError || error) && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30">
                <p className="text-xs text-red-700 dark:text-red-400">
                  {formError || error}
                </p>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={onCancel}
                disabled={submitting}
                className="flex-1 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              <button
                type="submit"
                disabled={
                  submitting ||
                  loading ||
                  !roomNumber ||
                  !roomTypeId
                }
                className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
              >
                {submitting ? "Creating..." : "Create Room"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </>
  );
}