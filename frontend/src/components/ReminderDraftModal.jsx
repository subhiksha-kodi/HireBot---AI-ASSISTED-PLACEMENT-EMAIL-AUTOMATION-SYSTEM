import { useState } from 'react';

function ReminderDraftModal({ reminder, draft, onClose, onApprove }) {
  const [editedDraft, setEditedDraft] = useState(draft);

  const handleApprove = () => {
    onApprove(editedDraft);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-xl">
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-slate-800">Draft Reminder Email</h3>
              <p className="text-sm text-red-600 font-medium mt-1">
                ⚠️ Draft – Requires Human Approval
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 text-xl"
            >
              ×
            </button>
          </div>
        </div>

        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <div className="text-sm text-amber-800">
              <strong>Reminder Context:</strong> {reminder.description}
            </div>
            <div className="text-sm text-amber-700 mt-1">
              <strong>Overdue by:</strong> {reminder.overdue_days} days
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">
              To: {reminder.contact_email}
            </label>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">Subject</label>
            <input
              type="text"
              value={editedDraft.subject}
              onChange={(e) => setEditedDraft({...editedDraft, subject: e.target.value})}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">Message</label>
            <textarea
              value={editedDraft.content}
              onChange={(e) => setEditedDraft({...editedDraft, content: e.target.value})}
              rows={8}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <div className="flex items-start gap-2">
              <span className="text-red-600">⚠️</span>
              <div className="text-sm text-red-800">
                <strong>Important:</strong> This is a suggested draft only. Please review and modify as needed before sending.
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-slate-200 bg-slate-50 rounded-b-xl">
          <div className="flex gap-3 justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-all font-medium"
            >
              Cancel
            </button>
            <button
              onClick={handleApprove}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-all font-medium"
            >
              Approve & Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReminderDraftModal;