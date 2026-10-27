/**
 * COGNITIVE UI component-library entry point.
 *
 * Import reusable, theme-aware primitives from this module rather than
 * reaching into implementation files. Domain components (workspace,
 * investigation, graph and acquisition views) stay in their own packages.
 */

export { Badge, StatusDot, type BadgeProps, type BadgeTone, type StatusDotProps } from "./Badge";
export {
  Button,
  IconButton,
  type ButtonProps,
  type ButtonSize,
  type ButtonVariant,
  type IconButtonProps,
} from "./Button";
export { ContextMenu, type ContextMenuItem } from "./ContextMenu";
export { DataTable, type DataTableColumn, type DataTableProps } from "./DataTable";
export {
  EmptyState,
  ErrorView,
  LoadingView,
  Skeleton,
  type EmptyStateProps,
  type ErrorViewProps,
  type LoadingViewProps,
  type SkeletonProps,
} from "./Feedback";
export { Icon, type IconName } from "./Icon";
export {
  Checkbox,
  Input,
  RadioGroup,
  Select,
  Textarea,
  type CheckboxProps,
  type InputProps,
  type RadioGroupProps,
  type RadioOption,
  type SelectOption,
  type SelectProps,
  type TextareaProps,
} from "./Input";
export { Modal, type ModalProps } from "./Modal";
export {
  Drawer,
  Popover,
  Tooltip,
  type DrawerProps,
  type PopoverProps,
  type TooltipProps,
} from "./Overlay";
export { Panel, type PanelProps, type PanelVariant } from "./Panel";
export { Tabs, type TabsItem, type TabsProps } from "./Tabs";
export { Toast, type ToastProps, type ToastTone } from "./Toast";
export { statusTone, type WorkStatus } from "./status";
