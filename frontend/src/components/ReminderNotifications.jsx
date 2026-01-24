import { useState, useEffect } from 'react';
import { checkPendingReminders, markReminderFulfilled, generateReminderDraft, sendEmail } from '../services/hrService';
import http from '../services/httpClient';
import ReminderDraftModal from './ReminderDraftModal';

function ReminderNotifications({ onClose, onCountChange }) {
  const [pendingReminders, setPendingReminders] = useState([]);
  const [visitReminders, setVisitReminders] = useState([]);
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [selectedReminder, setSelectedReminder] = useState(null);
  const [draftEmail, setDraftEmail] = useState(null);

  useEffect(() => {
    checkReminders();
    // Check every 5 minutes
    const interval = setInterval(() => {
      checkReminders();
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const checkReminders = async () => {
    try {
      const reminders = await checkPendingReminders();

      // Split into Visits and General Reminders
      const visits = reminders.filter(r =>
        r.description.toLowerCase().includes('visit') ||
        (r.due_date_str && r.due_date_str.toLowerCase().includes('visit'))
      );

      const others = reminders.filter(r =>
        !r.description.toLowerCase().includes('visit') &&
        (!r.due_date_str || !r.due_date_str.toLowerCase().includes('visit'))
      );

      setVisitReminders(visits);
      setPendingReminders(others);
      updateTotalCount(others.length, visits.length);
    } catch (error) {
      console.error('Failed to fetch reminders:', error);
    }
  };

  // Deprecated: checkVisitReminders merged above

  const updateTotalCount = (overdueCount, visitCount) => {
    if (onCountChange) {
      onCountChange(overdueCount + visitCount);
    }
  };

  const handleMarkFulfilled = async (reminderId) => {
    try {
      await markReminderFulfilled(reminderId);
      // Remove from both regular reminders and visit reminders
      const updatedReminders = pendingReminders.filter(r => r.id !== reminderId);
      const updatedVisits = visitReminders.filter(r => r.id !== reminderId);
      setPendingReminders(updatedReminders);
      setVisitReminders(updatedVisits);
      updateTotalCount(updatedReminders.length, updatedVisits.length);
    } catch (error) {
      console.error('Failed to mark reminder as fulfilled:', error);
    }
  };

  const handleSendReminder = async (reminder) => {
    try {
      console.log('Generating reminder draft for:', reminder);
      const draft = await generateReminderDraft(reminder.id);
      console.log('Draft generated:', draft);
      
      // Check if it's a date restriction error
      if (draft.error === 'date_restriction') {
        alert(`⚠️ Reminder Draft Unavailable\n\n${draft.message}`);
        return;
      }
      
      setSelectedReminder(reminder);
      setDraftEmail(draft);
      setShowDraftModal(true);
    } catch (error) {
      console.error('Failed to generate reminder draft:', error);
      alert('Failed to generate reminder draft. Please try again.');
    }
  };

  const handleApproveDraft = async (approvedDraft) => {
    try {
      await sendEmail(selectedReminder.contact_id, approvedDraft);
      await markReminderFulfilled(selectedReminder.id);
      const updatedReminders = pendingReminders.filter(r => r.id !== selectedReminder.id);
      setPendingReminders(updatedReminders);
      updateTotalCount(updatedReminders.length, visitReminders.length);
    } catch (error) {
      console.error('Failed to send reminder email:', error);
    }
  };

  const dismissVisitReminder = (id) => {
    const updatedVisits = visitReminders.filter(n => n.id !== id);
    setVisitReminders(updatedVisits);
    updateTotalCount(pendingReminders.length, updatedVisits.length);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden flex flex-col">
        <div className="bg-purple-50 border-b border-purple-200 p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"></div>
            <h4 className="text-lg font-semibold text-purple-800">Reminders & Commitments</h4>
          </div>
          <button
            onClick={onClose}
            className="text-purple-600 hover:text-purple-800 text-2xl font-bold"
          >
            ×
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {pendingReminders.length === 0 && visitReminders.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-lg font-medium">No reminders</p>
              <p className="text-sm mt-1">All commitments are up to date!</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Visit Reminders */}
              {visitReminders.map((notification) => (
                <div key={`visit-${notification.id}`} className="bg-purple-50 rounded-lg p-4 border border-purple-200">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></div>
                      <h4 className="text-sm font-semibold text-purple-800">
                        {notification.is_today ? '🔔 Today\'s Visit' :
                          notification.is_tomorrow ? '⏰ Tomorrow\'s Visit' :
                            `📅 Upcoming: ${notification.deadline_text}`}
                      </h4>
                    </div>
                    <button
                      onClick={() => dismissVisitReminder(notification.id)}
                      className="text-purple-600 hover:text-purple-800 text-xl font-bold"
                    >
                      ×
                    </button>
                  </div>

                  <div className="text-base text-gray-800 mb-2">
                    <strong>{notification.company_name}</strong> - {notification.contact_name}
                  </div>

                  <div className="text-sm text-gray-600 mb-3">
                    {notification.description}
                  </div>
                  
                  <div className="flex gap-3 mt-4">
                    <button
                      onClick={() => handleMarkFulfilled(notification.id)}
                      className="flex items-center gap-2 px-4 py-2 bg-green-100 text-green-700 text-sm font-medium rounded-lg hover:bg-green-200 transition-colors duration-200 shadow-sm border border-green-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Mark Fulfilled
                    </button>
                    <button
                      onClick={() => handleSendReminder(notification)}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-700 text-sm font-medium rounded-lg hover:bg-blue-200 transition-colors duration-200 shadow-sm border border-blue-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                      Draft Reminder
                    </button>
                  </div>
                </div>
              ))}

              {/* Overdue / Other Reminders */}
              {pendingReminders.map((reminder) => (
                <div key={`reminder-${reminder.id}`} className="bg-violet-50 rounded-lg p-4 border border-violet-200">
                  <div className="text-sm text-violet-700 font-medium mb-2">
                    {reminder.contact_name} • {reminder.company_name}
                  </div>
                  <div className="text-base text-gray-800 mb-2">
                    {reminder.description}
                  </div>
                  <div className="text-sm text-violet-600 mb-3">
                    Due: {reminder.deadline_text}
                  </div>
                  <div className="flex gap-3 mt-4">
                    <button
                      onClick={() => handleMarkFulfilled(reminder.id)}
                      className="flex items-center gap-2 px-4 py-2 bg-green-100 text-green-700 text-sm font-medium rounded-lg hover:bg-green-200 transition-colors duration-200 shadow-sm border border-green-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Mark Fulfilled
                    </button>
                    <button
                      onClick={() => handleSendReminder(reminder)}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-700 text-sm font-medium rounded-lg hover:bg-blue-200 transition-colors duration-200 shadow-sm border border-blue-200"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                      Draft Reminder
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showDraftModal && selectedReminder && draftEmail && (
        <ReminderDraftModal
          reminder={selectedReminder}
          draft={draftEmail}
          onClose={() => {
            setShowDraftModal(false);
            setSelectedReminder(null);
            setDraftEmail(null);
          }}
          onApprove={handleApproveDraft}
        />
      )}
    </div>
  );
}

export default ReminderNotifications;