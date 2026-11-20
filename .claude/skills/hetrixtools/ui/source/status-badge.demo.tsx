import { StatusBadge } from "@/components/ui/status-badge"
import {
  RiCheckboxCircleFill,
  RiCloseCircleFill,
  RiCloseCircleLine,
  RiShieldCheckLine,
} from '@remixicon/react'

export function StatusBadgeDemo() {
  return (
    <div className="flex flex-wrap justify-center gap-4">
      <StatusBadge 
        leftIcon={RiShieldCheckLine}
        rightIcon={RiCloseCircleLine}
        leftLabel="Protection"
        rightLabel="SSO login"
        status="success"
      />
      <StatusBadge 
        leftIcon={RiCheckboxCircleFill}
        rightIcon={RiCloseCircleLine}
        leftLabel="Live"
        rightLabel="Audit trails"
        status="success"
      />
      <StatusBadge 
        leftIcon={RiCloseCircleFill}
        rightIcon={RiShieldCheckLine}
        leftLabel="Safety checks"
        rightLabel="Production"
        status="error"
      />
    </div>
  )
}