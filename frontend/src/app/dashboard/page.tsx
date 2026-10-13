"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { recordPayment } from "@/services/payment";
import { getCurrentUser, logout } from "@/services/auth.service";
import { getDashboard } from "@/services/dashboard.service";
import {
  getRoomDetail,
  updateRoomStatus,
} from "@/services/room.service";
import { getRoomTypeOptions } from "@/services/room-type.service";
import {
  checkIn,
  checkOut,
  previewCheckIn,
  previewRoomChange,
  confirmRoomChange,
} from "@/services/stay.service";
import { BillingSummary } from "@/types/room";
import { RoomDetail } from "@/types/room";
import { User } from "@/types/auth";
import {
  DashboardResponse,
  RoomCard as RoomCardType,
} from "@/types/dashboard";
import {
  CheckInRequest,
  CheckInPreview,
  CheckoutResponse,
  ChangeRoomPreview,
  ChangeRoomResult,
} from "@/types/stay";

import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(
    null
  );
  const [selectedRoom, setSelectedRoom] = useState<RoomDetail | null>(
    null
  );
  const [roomLoading, setRoomLoading] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState("all");

  const [showCheckIn, setShowCheckIn] = useState(false);
  const [showCheckout, setShowCheckout] = useState(false);
  const [showChangeRoom, setShowChangeRoom] = useState(false);
  // ----------------------------------
  // Current User
  // ----------------------------------

  const {
    data: currentUser,
    isLoading: userLoading,
    isError: userError,
  } = useQuery<User>({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
  });

  // ----------------------------------
  // Dashboard
  // ----------------------------------

  const {
    data: dashboard,
    isLoading: dashboardLoading,
    isError: dashboardError,
  } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    refetchInterval: 20_000,
    refetchOnWindowFocus: true,
  });

  const {
    data: roomTypes = [],
    isLoading: roomTypesLoading,
    isError: roomTypesError,
  } = useQuery({
    queryKey: ["room-type-options"],
    queryFn: getRoomTypeOptions,
  });

  // ----------------------------------
  // Update Room Status
  // ----------------------------------

  const updateStatusMutation = useMutation({
    mutationFn: ({
      roomId,
      status,
    }: {
      roomId: number;
      status: string;
    }) => updateRoomStatus(roomId, status),

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["dashboard"],
      });

      if (selectedRoomId !== null) {
        const updatedRoom = await getRoomDetail(selectedRoomId);
        setSelectedRoom(updatedRoom);
      }
    },
  });

  // ----------------------------------
  // Check-in
  // ----------------------------------

  const checkInMutation = useMutation({
    mutationFn: (data: CheckInRequest) => checkIn(data),

    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["dashboard"],
      });

      setShowCheckIn(false);

      if (selectedRoomId !== null) {
        const updatedRoom = await getRoomDetail(selectedRoomId);
        setSelectedRoom(updatedRoom);
      }
    },
  });

// Payment mutation
const paymentMutation = useMutation({
  mutationFn: ({
    stayId,
    amount,
    method,
  }: {
    stayId: number;
    amount: string;
    method: string;
  }) =>
    recordPayment(stayId, {
      amount,
      method,
    }),

  onSuccess: async () => {
    await queryClient.invalidateQueries({
      queryKey: ["dashboard"],
    });

    if (selectedRoomId !== null) {
      const updatedRoom = await getRoomDetail(selectedRoomId);
      setSelectedRoom(updatedRoom);
    }
  },
});

  // ----------------------------------
// Check-out
// ----------------------------------

const checkOutMutation = useMutation({
  mutationFn: ({
    stayId,
    force,
  }: {
    stayId: number;
    force: boolean;
  }) => checkOut(stayId, force),

  onSuccess: async () => {
    await queryClient.invalidateQueries({
      queryKey: ["dashboard"],
    });

    setShowCheckout(false);

    if (selectedRoomId !== null) {
      const updatedRoom = await getRoomDetail(selectedRoomId);
      setSelectedRoom(updatedRoom);
    }
  },
});

// ----------------------------------
// Change Room
// ----------------------------------

const changeRoomMutation = useMutation({
  mutationFn: async ({
    stayId,
    newRoomId,
    finalPrice,
    force,
  }: {
    stayId: number;
    newRoomId: number;
    finalPrice: string;
    force: boolean;
  }) => {
    return confirmRoomChange(
      stayId,
      {
        new_room_id: newRoomId,
        final_price: finalPrice,
      },
      force
    );
  },

  onSuccess: async (result, variables) => {
    await queryClient.invalidateQueries({
      queryKey: ["dashboard"],
    });

    setShowChangeRoom(false);

    // If the room was split, the guest is now in the new room.
    // If it was simply updated, this is also the selected room.
    const newRoomId =
      result.new_stay?.room_id ??
      result.stay?.room_id ??
      variables.newRoomId;

    setSelectedRoomId(newRoomId);

    setRoomLoading(true);

    try {
      const updatedRoom = await getRoomDetail(newRoomId);
      setSelectedRoom(updatedRoom);
    } catch (error) {
      console.error("Failed to load new room:", error);
    } finally {
      setRoomLoading(false);
    }
  },
});

  // ----------------------------------
  // Logout
  // ----------------------------------

  async function handleLogout() {
    try {
      await logout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }

  // ----------------------------------
  // Open Room
  // ----------------------------------

  async function handleRoomClick(roomId: number) {
    setSelectedRoomId(roomId);
    setRoomLoading(true);
    setSelectedRoom(null);
    setShowCheckIn(false);

    try {
      const room = await getRoomDetail(roomId);
      setSelectedRoom(room);
    } catch (error) {
      console.error("Failed to load room:", error);
    } finally {
      setRoomLoading(false);
    }
  }

  // ----------------------------------
  // Update Room Status
  // ----------------------------------

  async function handleRoomStatusChange(status: string) {
    if (selectedRoomId === null) {
      return;
    }

    try {
      await updateStatusMutation.mutateAsync({
        roomId: selectedRoomId,
        status,
      });
    } catch (error) {
      console.error("Failed to update room status:", error);
    }
  }
  // Record payment
  async function handleRecordPayment(
    amount: string,
    method: string
  ): Promise<void> {
    if (
      selectedRoom?.stay_id === null ||
      selectedRoom?.stay_id === undefined
    ) {
      return;
    }

    await paymentMutation.mutateAsync({
      stayId: selectedRoom.stay_id,
      amount,
      method,
    });
  }
  // ----------------------------------
  // Loading
  // ----------------------------------

  if (dashboardLoading || userLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Loading dashboard...
        </p>
      </main>
    );
  }

  // ----------------------------------
  // Error
  // ----------------------------------

  if (
    dashboardError ||
    userError ||
    !dashboard ||
    !currentUser
  ) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
        <div className="rounded-lg border border-gray-200 bg-white px-6 py-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <p className="text-sm text-red-600 dark:text-red-400">
            Unable to load dashboard
          </p>
        </div>
      </main>
    );
  }

  const user = currentUser;
  const { summary, rooms } = dashboard;

  // ----------------------------------
  // Filter Rooms
  // ----------------------------------

  const filteredRooms =
    selectedStatus === "all"
      ? rooms
      : rooms.filter(
          (room) =>
            room.status.toLowerCase() === selectedStatus
        );

  const sortedRooms = [...filteredRooms].sort(
    (a, b) =>
      Number(a.room_number) - Number(b.room_number)
  );

  // ----------------------------------
  // UI
  // ----------------------------------

  return (
    <main className="min-h-screen bg-[#efe7d8] px-5 py-5 dark:bg-gray-950">
      <div className="mx-auto max-w-[1800px]">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold leading-tight text-gray-900 dark:text-white">
              Dashboard
            </h1>

            <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
              Welcome back, {user.name}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <ThemeToggle />

            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Summary */}
        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-6">
          <SummaryCard
            title="Total Rooms"
            value={summary.total_rooms}
            active={selectedStatus === "all"}
            onClick={() => setSelectedStatus("all")}
          />

          <SummaryCard
            title="Available"
            value={summary.available}
            active={selectedStatus === "available"}
            onClick={() => setSelectedStatus("available")}
          />

          <SummaryCard
            title="Occupied"
            value={summary.occupied}
            active={selectedStatus === "occupied"}
            onClick={() => setSelectedStatus("occupied")}
          />

          <SummaryCard
            title="Cleaning"
            value={summary.cleaning}
            active={selectedStatus === "cleaning"}
            onClick={() => setSelectedStatus("cleaning")}
          />

          <SummaryCard
            title="Maintenance"
            value={summary.maintenance}
            active={selectedStatus === "maintenance"}
            onClick={() => setSelectedStatus("maintenance")}
          />

          <SummaryCard
            title="Reserved"
            value={summary.reserved}
            active={selectedStatus === "reserved"}
            onClick={() => setSelectedStatus("reserved")}
          />
        </div>

        {/* Rooms Header */}
        <div className="mb-3 mt-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Rooms
          </h2>

          <p className="text-xs text-gray-500 dark:text-gray-400">
            {sortedRooms.length} rooms
          </p>
        </div>

        {/* Room Grid */}
        <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7">
          {sortedRooms.map((room) => (
            <RoomCard
              key={room.room_id}
              room={room}
              onClick={() =>
                handleRoomClick(room.room_id)
              }
            />
          ))}
        </div>
      </div>

      {/* Room Modal */}
      {selectedRoomId !== null && (
        <>
          <div
            className="fixed inset-0 z-40 animate-in bg-black/40 backdrop-blur-[2px] fade-in duration-200"
            onClick={() => {
              if (!showCheckIn && !showCheckout && !showChangeRoom) {
                setSelectedRoomId(null);
              }
            }}
          />

          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-200 dark:border-gray-800 dark:bg-gray-900">

              {roomLoading && (
                <div className="flex min-h-[300px] items-center justify-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Loading room details...
                  </p>
                </div>
              )}

              {!roomLoading && selectedRoom && (
                <>
                  {/* Room Header */}
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        Room
                      </p>

                      <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                        {selectedRoom.room_number}
                      </h2>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setSelectedRoomId(null);
                        setShowCheckIn(false);
                        setShowCheckout(false);
                        setShowChangeRoom(false);
                      }}
                      className="rounded-lg p-2 text-gray-500 transition-colors duration-150 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white"
                    >
                      ✕
                    </button>
                  </div>

                  {!showCheckIn && (
                    <RoomDetailPanel
                      room={selectedRoom}
                      onStatusChange={handleRoomStatusChange}
                      statusUpdating={updateStatusMutation.isPending}
                      onCheckIn={() => setShowCheckIn(true)}
                      onCheckOut={() => setShowCheckout(true)}
                      onChangeRoom={() => setShowChangeRoom(true)}
                      onRecordPayment={handleRecordPayment}
                      paymentSubmitting={paymentMutation.isPending}
                      paymentError={
                        paymentMutation.error instanceof Error
                          ? paymentMutation.error.message
                          : ""
                      }
                    />
                  )}

                  {showCheckIn && (
                    <CheckInForm
                      room={selectedRoom}
                      onCancel={() =>
                        setShowCheckIn(false)
                      }
                      onSubmit={(data) =>
                        checkInMutation.mutate(data)
                      }
                      submitting={
                        checkInMutation.isPending
                      }
                      submitError={
                        checkInMutation.isError
                          ? checkInMutation.error instanceof Error
                            ? checkInMutation.error.message
                            : "Check-in failed"
                          : ""
                      }
                    />
                  )}
                  {showCheckout && (
                    <CheckoutForm
                      room={selectedRoom}
                      onCancel={() => {
                        setShowCheckout(false);
                      }}
                      onConfirm={(force) => {
                        const stayId = selectedRoom.stay_id;

                        if (stayId == null) {
                          console.error("Checkout failed: no stay_id", selectedRoom);
                          return;
                        }

                        checkOutMutation.mutate({
                          stayId,
                          force,
                        });
                      }}
                      submitting={checkOutMutation.isPending}
                      submitError={
                        checkOutMutation.isError
                          ? checkOutMutation.error instanceof Error
                            ? checkOutMutation.error.message
                            : "Checkout failed"
                          : ""
                      }
                    />
                  )}
                  {showChangeRoom && (
                    <ChangeRoomForm
                      room={selectedRoom}
                      availableRooms={rooms.filter(
                        (room) =>
                          room.status.toLowerCase() === "available" &&
                          room.room_id !== selectedRoom.room_id
                      )}
                      onCancel={() => {
                        setShowChangeRoom(false);
                      }}
                      onConfirm={(data) => {
                        const stayId = selectedRoom.stay_id;

                        if (stayId == null) {
                          console.error(
                            "Change room failed: no stay_id",
                            selectedRoom
                          );
                          return;
                        }

                        changeRoomMutation.mutate({
                          stayId,
                          newRoomId: data.newRoomId,
                          finalPrice: data.finalPrice,
                          force: data.force,
                        });
                      }}
                      submitting={changeRoomMutation.isPending}
                      submitError={
                        changeRoomMutation.isError
                          ? changeRoomMutation.error instanceof Error
                            ? changeRoomMutation.error.message
                            : "Change room failed"
                          : ""
                      }
                    />
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </main>
  );
}

/* ---------------------------------- */
/* Summary Card                        */
/* ---------------------------------- */

function SummaryCard({
  title,
  value,
  active = false,
  onClick,
}: {
  title: string;
  value: number;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        cursor-pointer rounded-lg border px-4 py-3 text-left
        transition-all duration-150
        ${
          active
            ? "border-gray-400 bg-gray-100 shadow-sm dark:border-gray-600 dark:bg-gray-800"
            : "border-gray-200 bg-white shadow-sm hover:border-gray-300 hover:bg-gray-50 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700 dark:hover:bg-gray-800"
        }
      `}
    >
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
        {title}
      </p>

      <p className="mt-1 text-2xl font-bold leading-none text-gray-900 dark:text-white">
        {value}
      </p>
    </button>
  );
}

/* ---------------------------------- */
/* Room Card                           */
/* ---------------------------------- */

const STATUS_STYLES: Record<
  string,
  {
    bg: string;
    text: string;
    dot: string;
  }
> = {
  available: {
    bg: "bg-green-50 dark:bg-green-950",
    text: "text-green-700 dark:text-green-400",
    dot: "bg-green-500",
  },

  occupied: {
    bg: "bg-blue-50 dark:bg-blue-950",
    text: "text-blue-700 dark:text-blue-400",
    dot: "bg-blue-500",
  },

  cleaning: {
    bg: "bg-yellow-50 dark:bg-yellow-950",
    text: "text-yellow-700 dark:text-yellow-400",
    dot: "bg-yellow-500",
  },

  maintenance: {
    bg: "bg-red-50 dark:bg-red-950",
    text: "text-red-700 dark:text-red-400",
    dot: "bg-red-500",
  },
};

function RoomCard({
  room,
  onClick,
}: {
  room: RoomCardType;
  onClick: () => void;
}) {
  const style =
    STATUS_STYLES[room.status.toLowerCase()] ?? {
      bg: "bg-gray-100 dark:bg-gray-800",
      text: "text-gray-600 dark:text-gray-300",
      dot: "bg-gray-400",
    };

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-[125px] cursor-pointer flex-col items-start overflow-hidden rounded-lg border border-gray-200 bg-white p-3 text-left shadow-sm transition hover:border-gray-300 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700"
    >
      <div className="flex w-full items-center justify-between gap-2">
        <h3 className="text-base font-bold leading-none text-gray-900 dark:text-white">
          {room.room_number}
        </h3>

        <span
          className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${style.bg} ${style.text}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${style.dot}`}
          />

          {room.status}
        </span>
      </div>

      <p className="mt-2 w-full truncate text-xs leading-tight text-gray-500 dark:text-gray-400">
        {room.room_type_name}
      </p>

      <div className="mt-2 h-5 w-full">
        {room.guest_name && (
          <p className="truncate text-sm font-medium leading-tight text-gray-900 dark:text-white">
            {room.guest_name}
          </p>
        )}
      </div>

      {room.nightly_rate !== null && (
        <p className="mt-1.5 text-xs font-medium leading-tight text-gray-700 dark:text-gray-300">
          ₹{Number(room.nightly_rate)}/night
        </p>
      )}

      {room.nightly_rate === null &&
        room.min_price !== null &&
        room.max_price !== null && (
          <p className="mt-2 text-xs font-medium text-gray-700 dark:text-gray-300">
            {room.min_price === room.max_price
              ? `₹${Number(room.min_price)}/night`
              : `₹${Number(room.min_price)}–₹${Number(
                  room.max_price
                )}/night`}
          </p>
        )}
    </button>
  );
}

function PaymentForm({
  billing,
  onCancel,
  onSubmit,
  submitting,
  submitError,
}: {
  billing: BillingSummary;
  onCancel: () => void;
  onSubmit: (amount: string, method: string) => Promise<void>;
  submitting: boolean;
  submitError: string;
}) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");

  async function handleSubmit(
  event: React.FormEvent<HTMLFormElement>
) {
  event.preventDefault();

  if (!amount) {
    return;
  }

  const numericAmount = Number(amount);

  if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
    return;
  }

  try {
    await onSubmit(amount, method);
    onCancel();
  } catch {
    // Payment failed.
    // Keep the form open so the user can retry.
  }
}

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <div className="space-y-4">
        {/* Amount */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Payment amount
          </label>

          <div className="relative mt-1.5">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
              ₹
            </span>

            <input
              type="text"
              inputMode="decimal"
              value={amount}
              onChange={(event) => {
                const value = event.target.value;

                if (/^\d*\.?\d{0,2}$/.test(value)) {
                  setAmount(value);
                }
              }}
              placeholder="0.00"
              className="w-full rounded-lg border border-gray-200 bg-gray-50 py-2.5 pl-8 pr-3 text-sm text-gray-900 outline-none transition focus:border-gray-400 focus:ring-1 focus:ring-gray-300 dark:border-gray-700 dark:bg-gray-950 dark:text-white dark:focus:border-gray-500"
              disabled={submitting}
            />
          </div>

          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            Balance due: ₹{Number(billing.balance)}
          </p>
        </div>

        {/* Method */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Payment method
          </label>

          <select
            value={method}
            onChange={(event) => setMethod(event.target.value)}
            disabled={submitting}
            className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-900 outline-none transition focus:border-gray-400 focus:ring-1 focus:ring-gray-300 dark:border-gray-700 dark:bg-gray-950 dark:text-white dark:focus:border-gray-500"
          >
            <option value="cash">Cash</option>
            <option value="upi">UPI</option>
            <option value="card">Card</option>
          </select>
        </div>

        {/* Error */}
        {submitError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30">
            <p className="text-xs text-red-700 dark:text-red-400">
              {submitError}
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Cancel
          </button>

          <button
            type="submit"
            disabled={submitting || !amount}
            className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
          >
            {submitting ? "Recording..." : "Record Payment"}
          </button>
        </div>
      </div>
    </form>
  );
}
/* ---------------------------------- */
/* Room Detail Panel                   */
/* ---------------------------------- */

function RoomDetailPanel({
  room,
  onStatusChange,
  statusUpdating,
  onCheckIn,
  onCheckOut,
  onChangeRoom,
  onRecordPayment,
  paymentSubmitting,
  paymentError,
}: {
  room: RoomDetail;
  onStatusChange: (status: string) => void;
  statusUpdating: boolean;
  onCheckIn: () => void;
  onCheckOut: () => void;
  onChangeRoom: () => void;
  onRecordPayment: (amount: string, method: string) => Promise<void>;
  paymentSubmitting: boolean;
  paymentError: string;
}) {
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const isOccupied =
    room.status.toLowerCase() === "occupied";

  return (
    <div className="mt-8 space-y-6">

      {/* Status */}
      <div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Status
        </p>

        <div className="mt-2 flex flex-wrap gap-2">
          {[
            "available",
            "cleaning",
            "maintenance",
          ].map((status) => (
            <button
              key={status}
              type="button"
              disabled={
                statusUpdating || isOccupied
              }
              onClick={() =>
                onStatusChange(status)
              }
              className={`
                rounded-lg border px-3 py-2 text-sm font-medium capitalize
                transition
                ${
                  room.status.toLowerCase() === status
                    ? "border-gray-400 bg-gray-100 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
                }
                disabled:cursor-not-allowed disabled:opacity-50
              `}
            >
              {status}
            </button>
          ))}
        </div>

        {isOccupied && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            An occupied room cannot have its operational
            status changed.
          </p>
        )}
      </div>

      {/* Check In */}
      {room.status.toLowerCase() === "available" && (
        <button
          type="button"
          onClick={onCheckIn}
          className="w-full rounded-lg bg-gray-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
        >
          Check In
        </button>
      )}
      {/*Check out */}
      {isOccupied && (
        <button
          type="button"
          onClick={() => {
            console.log("CHECKOUT BUTTON CLICKED");
            onCheckOut();
          }}
          className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:hover:bg-gray-800"
        >
          Check Out
        </button>
      )}
      {/*Change room */}
      {isOccupied && (
        <button
          type="button"
          onClick={onChangeRoom}
          className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:hover:bg-gray-800"
        >
          Change Room
        </button>
      )}
      {/* Guest */}
      {room.guest && (
        <>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Guest
            </p>

            <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">
              {room.guest.full_name}
            </p>
          </div>

          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Phone
            </p>

            <p className="mt-1 text-gray-900 dark:text-gray-200">
              {room.guest.phone}
            </p>
          </div>
        </>
      )}

      {/* Check-in */}
      {room.actual_check_in_at && (
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Check-in
          </p>

          <p className="mt-1 text-gray-900 dark:text-gray-200">
            {new Intl.DateTimeFormat("en-IN", {
              dateStyle: "short",
              timeStyle: "short",
            }).format(
              new Date(room.actual_check_in_at)
            )}
          </p>
        </div>
      )}

      {/* Expected checkout */}
      {room.expected_checkout_at && (
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Expected checkout
          </p>

          <p className="mt-1 text-gray-900 dark:text-gray-200">
            {new Intl.DateTimeFormat("en-IN", {
              dateStyle: "short",
              timeStyle: "short",
            }).format(
              new Date(room.expected_checkout_at)
            )}
          </p>
        </div>
      )}

          {/* Billing */}
          {room.billing && (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  Billing
                </p>

                <span
                  className={`rounded-full px-2.5 py-1 text-[11px] font-medium capitalize ${
                    room.billing.status === "paid"
                      ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400"
                      : room.billing.status === "partial"
                      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-400"
                      : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
                  }`}
                >
                  {room.billing.status}
                </span>
              </div>

              <div className="mt-3 space-y-2">
                <BillingRow
                  label="Occupancy"
                  value={`${room.billing.occupancy} ${
                    room.billing.occupancy === 1 ? "guest" : "guests"
                  }`}
                />

                <BillingRow
                  label="Nightly rate"
                  value={`₹${Number(room.billing.nightly_rate)}`}
                />

                <BillingRow
                  label="Nights"
                  value={String(room.billing.nights)}
                />

                <BillingRow
                  label="Total"
                  value={`₹${Number(room.billing.total)}`}
                />

                <BillingRow
                  label="Paid"
                  value={`₹${Number(room.billing.paid)}`}
                />

                <BillingRow
                  label="Balance"
                  value={`₹${Number(room.billing.balance)}`}
                />
              </div>

              {/* Record payment */}
              {!showPaymentForm && (
                <button
                  type="button"
                  onClick={() => setShowPaymentForm(true)}
                  className="mt-4 w-full rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
                >
                  Record Payment
                </button>
              )}

              {/* Payment form */}
              {showPaymentForm && (
                <PaymentForm
                  billing={room.billing}
                  onCancel={() => setShowPaymentForm(false)}
                  onSubmit={onRecordPayment}
                  submitting={paymentSubmitting}
                  submitError={paymentError}
                />
              )}
            </div>
          )}
    </div>
  );
}

/* ---------------------------------- */
/* Change Room Form                   */
/* ---------------------------------- */

function ChangeRoomForm({
  room,
  availableRooms,
  onCancel,
  onConfirm,
  submitting,
  submitError,
}: {
  room: RoomDetail;
  availableRooms: RoomCardType[];
  onCancel: () => void;
  onConfirm: (data: {
    newRoomId: number;
    finalPrice: string;
    force: boolean;
  }) => void;
  submitting: boolean;
  submitError: string;
}) {
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [finalPrice, setFinalPrice] = useState("");
  const [force, setForce] = useState(false);

  const [preview, setPreview] =
    useState<ChangeRoomPreview | null>(null);

  const [previewLoading, setPreviewLoading] =
    useState(false);

  const [previewError, setPreviewError] =
    useState("");

  async function handleRoomChange(
    event: React.ChangeEvent<HTMLSelectElement>
  ) {
    const roomId = event.target.value;

    setSelectedRoomId(roomId);
    setPreview(null);
    setPreviewError("");
    setFinalPrice("");
    setForce(false);

    if (!roomId) {
      return;
    }

    try {
      setPreviewLoading(true);

      const result = await previewRoomChange(
        room.stay_id!,
        Number(roomId)
      );

      setPreview(result);

      if (result.suggested_price !== null) {
        setFinalPrice(result.suggested_price);
      }
    } catch (error) {
      setPreviewError(
        error instanceof Error
          ? error.message
          : "Unable to preview room change"
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (!selectedRoomId) {
      return;
    }

    const price = Number(finalPrice);

    if (!finalPrice || Number.isNaN(price) || price <= 0) {
      setPreviewError(
        "Please enter a valid final price."
      );
      return;
    }

    onConfirm({
      newRoomId: Number(selectedRoomId),
      finalPrice,
      force,
    });
  }

  const oldBalance =
    preview?.old_balance_due_if_split !== null
      ? Number(preview?.old_balance_due_if_split ?? 0)
      : 0;

  const hasOutstandingBalance =
    preview?.mode === "split" && oldBalance > 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-8 space-y-6"
    >
      {/* Header */}
      <div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Change Room
        </p>

        <h3 className="mt-1 text-xl font-semibold text-gray-900 dark:text-white">
          Move guest to another room
        </h3>

        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Current room: {room.room_number}
        </p>
      </div>

      {/* Available rooms */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          New room
        </label>

        <select
          value={selectedRoomId}
          onChange={handleRoomChange}
          disabled={submitting || previewLoading}
          className="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
        >
          <option value="">
            Select an available room
          </option>

          {availableRooms.map((availableRoom) => (
            <option
              key={availableRoom.room_id}
              value={availableRoom.room_id}
            >
              Room {availableRoom.room_number} —{" "}
              {availableRoom.room_type_name}
            </option>
          ))}
        </select>

        {availableRooms.length === 0 && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            No available rooms.
          </p>
        )}
      </div>
      {previewError && (
  <div className="mt-2 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30">
    <p className="text-xs text-red-700 dark:text-red-400">
      {previewError}
    </p>

    {selectedRoomId && (
      <button
        type="button"
        onClick={() => {
          const roomId = Number(selectedRoomId);

          setPreviewError("");
          setPreview(null);
          setPreviewLoading(true);

          previewRoomChange(room.stay_id!, roomId)
            .then((result) => {
              setPreview(result);

              if (result.suggested_price !== null) {
                setFinalPrice(result.suggested_price);
              }
            })
            .catch((error) => {
              setPreviewError(
                error instanceof Error
                  ? error.message
                  : "Unable to check this room"
              );
            })
            .finally(() => {
              setPreviewLoading(false);
            });
        }}
        className="shrink-0 text-xs font-medium text-red-700 underline underline-offset-2 dark:text-red-400"
      >
        Retry
      </button>
    )}
  </div>
)}
      {/* Preview loading */}
      {previewLoading && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
          Checking room change...
        </div>
      )}

      {/* Preview */}
      {preview && !previewLoading && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Change summary
          </p>

          <div className="mt-3 space-y-2">
            <BillingRow
              label="Change type"
              value={
                preview.mode === "updated"
                  ? "Update current stay"
                  : "Split stay"
              }
            />

            {preview.suggested_price !== null && (
              <BillingRow
                label="Suggested price"
                value={`₹${Number(
                  preview.suggested_price
                )}`}
              />
            )}

            {preview.mode === "split" && (
              <BillingRow
                label="Current room balance"
                value={
                  preview.old_balance_due_if_split !== null
                    ? `₹${Number(
                        preview.old_balance_due_if_split
                      )}`
                    : "₹0"
                }
              />
            )}
          </div>
        </div>
      )}

      {/* Final price */}
      {preview && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Final nightly price
          </label>

          <div className="relative mt-2">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-500 dark:text-gray-400">
              ₹
            </span>

            <input
              type="number"
              min="1"
              step="0.01"
              value={finalPrice}
              onChange={(event) =>
                setFinalPrice(event.target.value)
              }
              required
              disabled={submitting}
              className="w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-8 pr-3 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              placeholder="Enter final price"
            />
          </div>

          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            You can adjust this price if the guest negotiated a different rate.
          </p>
        </div>
      )}

      {/* Outstanding balance */}
      {hasOutstandingBalance && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
          <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
            Outstanding balance
          </p>

          <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
            The current room has an outstanding balance of{" "}
            <strong>₹{oldBalance}</strong>.
          </p>

          <label className="mt-3 flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={force}
              onChange={(event) =>
                setForce(event.target.checked)
              }
              disabled={submitting}
              className="mt-0.5 h-4 w-4 rounded border-gray-300"
            />

            <span className="text-sm text-amber-800 dark:text-amber-300">
              Allow room change without settling this balance
            </span>
          </label>
        </div>
      )}


      {/* Actions */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:hover:bg-gray-800"
        >
          Cancel
        </button>

        <button
          type="submit"
          disabled={
            submitting ||
            previewLoading ||
            !selectedRoomId ||
            !preview ||
            (hasOutstandingBalance && !force)
          }
          className="flex-1 rounded-lg bg-gray-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
        >
          {submitting
            ? "Changing..."
            : "Confirm Change"}
        </button>
      </div>
    </form>
  );
}

/* ---------------------------------- */
/* Check-in Form                       */
/* ---------------------------------- */

function CheckInForm({
  room,
  onCancel,
  onSubmit,
  submitting,
  submitError,
}: {
  room: RoomDetail;
  onCancel: () => void;
  onSubmit: (data: CheckInRequest) => void;
  submitting: boolean;
  submitError: string;
}) {
  const [guestFullName, setGuestFullName] = useState("");
  const [guestPhone, setGuestPhone] = useState("");
  const now = new Date();
  const [checkInDate, setCheckInDate] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
      now.getDate()
    ).padStart(2, "0")}`
  );

  const [checkInHour, setCheckInHour] = useState(
    String(now.getHours() % 12 || 12).padStart(2, "0")
  );

  const [checkInMinute, setCheckInMinute] = useState(
    String(now.getMinutes()).padStart(2, "0")
  );

  const [checkInPeriod, setCheckInPeriod] = useState(
    now.getHours() >= 12 ? "PM" : "AM"
  );
  const [guestEmail, setGuestEmail] = useState("");
  const [guestAddress, setGuestAddress] = useState("");

  // Keep these as strings so the user can type/delete freely.
  const [occupancy, setOccupancy] = useState("1");
  const [stayHours, setStayHours] = useState("24");

  const [price, setPrice] = useState("");

  const [capacity, setCapacity] = useState<number | null>(
    null
  );

  const [previewLoading, setPreviewLoading] =
    useState(false);

  const [previewError, setPreviewError] =
    useState("");

  const previewRequestId = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ----------------------------------
  // Preview occupancy
  // ----------------------------------

async function loadPreview(occupancyValue: string) {
  setPreviewError("");

  if (occupancyValue === "") {
    setPrice("");
    return;
  }

  const occupancyNumber = Number(occupancyValue);

  if (!Number.isInteger(occupancyNumber) || occupancyNumber <= 0) {
    setPrice("");
    return;
  }

  if (capacity !== null && occupancyNumber > capacity) {
    setPrice("");
    setPreviewError(
      `Maximum occupancy for this room is ${capacity} ${
        capacity === 1 ? "guest" : "guests"
      }.`
    );
    return;
  }

  const requestId = ++previewRequestId.current;
  setPreviewLoading(true);

  try {
    const preview = await previewCheckIn(room.room_id, occupancyNumber);

    if (requestId !== previewRequestId.current) {
      return;
    }

    setCapacity(preview.capacity);

    if (occupancyNumber > preview.capacity) {
      setPrice("");
      setPreviewError(
        `Maximum occupancy for this room is ${preview.capacity} ${
          preview.capacity === 1 ? "guest" : "guests"
        }.`
      );
      return;
    }

    setPrice(preview.suggested_price !== null ? preview.suggested_price : "");
  } catch (error) {
    if (requestId !== previewRequestId.current) {
      return;
    }
    setPrice("");
    setPreviewError(
      error instanceof Error ? error.message : "Unable to validate occupancy."
    );
  } finally {
    if (requestId === previewRequestId.current) {
      setPreviewLoading(false);
    }
  }
}
  // ----------------------------------
  // Automatically load capacity
  // ----------------------------------

  useEffect(() => {
  void loadPreview("1");
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [room.room_id]);

  // ----------------------------------
  // Occupancy Change
  // ----------------------------------

function handleOccupancyChange(value: string) {
  setOccupancy(value);

  if (value === "") {
    setPrice("");
    setPreviewError("");
    return;
  }

  const numericValue = Number(value);

  if (!Number.isInteger(numericValue) || numericValue <= 0) {
    setPrice("");
    setPreviewError("Occupancy must be at least 1.");
    return;
  }

  if (capacity !== null && numericValue > capacity) {
    setPrice("");
    setPreviewError(
      `Maximum occupancy for this room is ${capacity} ${
        capacity === 1 ? "guest" : "guests"
      }.`
    );
    return;
  }

  if (debounceRef.current) {
    clearTimeout(debounceRef.current);
  }
  debounceRef.current = setTimeout(() => {
    loadPreview(value);
  }, 300);
}

  // ----------------------------------
  // Submit
  // ----------------------------------

  function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    const occupancyNumber = Number(
      occupancy
    );

    const stayHoursNumber = Number(
      stayHours
    );

    if (
      !Number.isInteger(occupancyNumber) ||
      occupancyNumber <= 0
    ) {
      setPreviewError(
        "Please enter a valid occupancy."
      );
      return;
    }

    if (
      capacity !== null &&
      occupancyNumber > capacity
    ) {
      setPreviewError(
        `Maximum occupancy for this room is ${capacity} ${
          capacity === 1 ? "guest" : "guests"
        }.`
      );
      return;
    }

    if (
      !Number.isInteger(stayHoursNumber) ||
      stayHoursNumber <= 0
    ) {
      return;
    }

    if (
      !guestFullName.trim() ||
      !guestPhone.trim()
    ) {
      return;
    }

    if (
      !price ||
      Number(price) <= 0
    ) {
      return;
    }
    const hour12 = Number(checkInHour);

    let hour24 = hour12;

    if (checkInPeriod === "AM" && hour12 === 12) {
      hour24 = 0;
    }

    if (checkInPeriod === "PM" && hour12 !== 12) {
      hour24 = hour12 + 12;
    }

    const checkInDateTime = new Date(
      `${checkInDate}T${String(hour24).padStart(2, "0")}:${checkInMinute}:00`
    );
    onSubmit({
      room_id: room.room_id,
      guest_full_name:
        guestFullName.trim(),
      guest_phone:
        guestPhone.trim(),
      guest_email:
        guestEmail.trim() || null,
      guest_address:
        guestAddress.trim() || null,
      occupancy: occupancyNumber,
      stay_hours: stayHoursNumber,
      agreed_price: price,
      actual_check_in_at:
        checkInDateTime.toISOString(),
    });
  }

  const occupancyNumber = Number(
    occupancy
  );

  const occupancyInvalid =
    occupancy === "" ||
    !Number.isInteger(occupancyNumber) ||
    occupancyNumber <= 0 ||
    (capacity !== null &&
      occupancyNumber > capacity);

  return (
    <div className="mt-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Check-in
          </p>

          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            Room {room.room_number}
          </h3>
        </div>

        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
        >
          ✕
        </button>
      </div>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="mt-6 space-y-4"
      >

        {/* Guest Name */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Guest name
          </label>

          <input
            type="text"
            value={guestFullName}
            onChange={(event) =>
              setGuestFullName(
                event.target.value
              )
            }
            required
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>

        {/* Phone */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Phone
          </label>

          <input
            type="tel"
            value={guestPhone}
            onChange={(event) =>
              setGuestPhone(
                event.target.value
              )
            }
            required
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>
        {/*Check in time */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Check-in date & time
          </label>

          <div className="mt-1 grid grid-cols-[1.4fr_0.8fr_0.8fr_0.8fr] gap-2">
            {/* Date */}
            <input
              type="date"
              value={checkInDate}
              onChange={(event) => setCheckInDate(event.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />

            {/* Hour */}
            <input
              type="text"
              inputMode="numeric"
              maxLength={2}
              value={checkInHour}
              onChange={(event) => {
                const value = event.target.value.replace(/\D/g, "");

                if (value === "" || Number(value) <= 12) {
                  setCheckInHour(value);
                }
              }}
              placeholder="HH"
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />

            {/* Minute */}
            <input
              type="text"
              inputMode="numeric"
              maxLength={2}
              value={checkInMinute}
              onChange={(event) => {
                const value = event.target.value.replace(/\D/g, "");

                if (value === "" || Number(value) <= 59) {
                  setCheckInMinute(value);
                }
              }}
              placeholder="MM"
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            />

            {/* AM / PM */}
            <select
              value={checkInPeriod}
              onChange={(event) => setCheckInPeriod(event.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
            >
              <option value="AM">AM</option>
              <option value="PM">PM</option>
            </select>
          </div>
        </div>
        {/* Email */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Email
          </label>

          <input
            type="email"
            value={guestEmail}
            onChange={(event) =>
              setGuestEmail(
                event.target.value
              )
            }
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>

        {/* Address */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Address
          </label>

          <textarea
            value={guestAddress}
            onChange={(event) =>
              setGuestAddress(
                event.target.value
              )
            }
            rows={2}
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>

        {/* Occupancy */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Occupancy
          </label>

          <input
            type="number"
            min={1}
            max={capacity ?? undefined}
            value={occupancy}
            onChange={(event) =>
              handleOccupancyChange(
                event.target.value
              )
            }
            required
            className={`
              mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm text-gray-900 outline-none dark:bg-gray-950 dark:text-white
              ${
                capacity !== null &&
                occupancyNumber > capacity
                  ? "border-red-500 focus:border-red-500"
                  : "border-gray-300 focus:border-gray-500 dark:border-gray-700"
              }
            `}
          />

          {capacity !== null && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Maximum occupancy:{" "}
              {capacity}{" "}
              {capacity === 1
                ? "guest"
                : "guests"}
            </p>
          )}

          {previewError && (
            <p className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">
              {previewError}
            </p>
          )}

          {previewLoading && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Checking occupancy and price...
            </p>
          )}
        </div>

        {/* Stay Hours */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Stay hours
          </label>

          <input
            type="number"
            min={1}
            value={stayHours}
            onChange={(event) =>
              setStayHours(
                event.target.value
              )
            }
            required
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>

        {/* Price */}
        <div>
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Nightly price
          </label>

          <input
            type="number"
            min={0}
            step="0.01"
            value={price}
            onChange={(event) =>
              setPrice(
                event.target.value
              )
            }
            required
            className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </div>

        {/* Mutation Error */}
        {submitError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
            {submitError}
          </div>
        )}

        {/* Buttons */}
        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Cancel
          </button>

          <button
            type="submit"
            disabled={
              submitting ||
              previewLoading ||
              occupancyInvalid ||
              !price
            }
            className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
          >
            {submitting
              ? "Checking in..."
              : "Check In"}
          </button>
        </div>
      </form>
    </div>
  );
}
function CheckoutForm({
  room,
  onCancel,
  onConfirm,
  submitting,
  submitError,
}: {
  room: RoomDetail;
  onCancel: () => void;
  onConfirm: (force: boolean) => void;
  submitting: boolean;
  submitError: string;
}) {
  const billing = room.billing;

  if (!billing) {
    return (
      <div className="mt-8">
        <p className="text-sm text-red-600 dark:text-red-400">
          Billing information is unavailable.
        </p>

        <button
          type="button"
          onClick={onCancel}
          className="mt-4 w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium dark:border-gray-700"
        >
          Close
        </button>
      </div>
    );
  }

  const balance = Number(billing.balance);
  const hasOutstandingBalance = balance > 0;

  return (
    <div className="mt-8">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Check-out
          </p>

          <h3 className="text-xl font-bold text-gray-900 dark:text-white">
            Room {room.room_number}
          </h3>
        </div>

        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"
        >
          ✕
        </button>
      </div>

      <div className="mt-6 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950">
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
          Final billing
        </p>

        <div className="mt-3 space-y-2">
          <BillingRow
            label="Occupancy"
            value={`${billing.occupancy} ${
              billing.occupancy === 1 ? "guest" : "guests"
            }`}
          />
          <BillingRow
            label="Nightly rate"
            value={`₹${Number(billing.nightly_rate)}`}
          />

          <BillingRow
            label="Nights"
            value={String(billing.nights)}
          />

          <BillingRow
            label="Total"
            value={`₹${Number(billing.total)}`}
          />

          <BillingRow
            label="Paid"
            value={`₹${Number(billing.paid)}`}
          />

          <div className="border-t border-gray-200 pt-2 dark:border-gray-800">
            <BillingRow
              label="Balance"
              value={`₹${balance}`}
            />
          </div>
        </div>
      </div>

      {hasOutstandingBalance && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-950">
          <p className="text-sm font-medium text-red-700 dark:text-red-400">
            Outstanding balance: ₹{balance}
          </p>

          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            The guest has not fully paid the bill.
          </p>
        </div>
      )}

      {!hasOutstandingBalance && (
        <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-900 dark:bg-green-950">
          <p className="text-sm font-medium text-green-700 dark:text-green-400">
            Payment settled
          </p>

          <p className="mt-1 text-xs text-green-600 dark:text-green-400">
            The guest has paid the full amount.
          </p>
        </div>
      )}

      {submitError && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {submitError}
        </div>
      )}

      <div className="mt-6 flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          Cancel
        </button>

        {hasOutstandingBalance ? (
          <button
            type="button"
            onClick={() => onConfirm(true)}
            disabled={submitting}
            className="flex-1 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Checking out..." : "Force Checkout"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onConfirm(false)}
            disabled={submitting}
            className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
          >
            {submitting ? "Checking out..." : "Confirm Checkout"}
          </button>
        )}
      </div>
    </div>
  );
}
/* ---------------------------------- */
/* Billing Row                         */
/* ---------------------------------- */

function BillingRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-gray-500 dark:text-gray-400">
        {label}
      </span>

      <span className="font-medium text-gray-900 dark:text-white">
        {value}
      </span>
    </div>
  );
}









