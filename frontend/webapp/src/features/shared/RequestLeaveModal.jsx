import { LogOut } from 'lucide-react'
import { requestLeave } from '@/api/shared'
import { useAction } from '@/hooks/useAction'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

export function RequestLeaveModal({ plan, onClose }) {
  const send = useAction(() => requestLeave(plan.id), { onSuccess: onClose, tone: 'pending' })
  const owner = plan.owner.firstName
  return (
    <Modal
      open
      onClose={onClose}
      title="Ask to leave?"
      subtitle={plan.planName}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="reject" icon={LogOut} busy={send.busy} onClick={() => send.run()}>
            Send request
          </Button>
        </>
      }
    >
      <p>
        {owner} decides when you leave and what happens to anything unpaid. You stay in the plan, and keep your seat, until {owner} approves.
      </p>
    </Modal>
  )
}
