import { useState, useEffect, useRef } from "react";
import { parseHrReply, sendEmail } from "../services/hrService";

function EmailConversationModal({ contact, onClose, onRefresh }) {
  const [conversations, setConversations] = useState([]);
  const conversationEndRef = useRef(null);
  const didInitialScroll = useRef(false);
  const [latestHrReply, setLatestHrReply] = useState(null);

  useEffect(() => {
    console.log('=== EmailConversationModal useEffect ===');
    console.log('Contact data received:', contact);

    if (contact?.conversation && Array.isArray(contact.conversation)) {
      console.log('Processing', contact.conversation.length, 'conversation items');

      const mappedConversations = contact.conversation.map((conv, index) => {
        let timestamp = new Date();
        if (conv.timestamp) {
          timestamp = typeof conv.timestamp === 'number' ? new Date(conv.timestamp) : new Date(conv.timestamp);
        } else if (conv.sent_at) {
          timestamp = typeof conv.sent_at === 'number' ? new Date(conv.sent_at) : new Date(conv.sent_at);
        }

        return {
          id: conv.id || `${Date.now()}-${Math.random()}`,
          message: conv.content || conv.message || '',
          type: conv.direction || 'sent',
          timestamp: timestamp,
          subject: conv.subject || '',
          direction: conv.direction
        };
      });

      // Remove duplicates based on message content, subject, and direction
      const uniqueConversations = mappedConversations.filter((conv, index, self) => {
        return index === self.findIndex(c => 
          c.message.trim() === conv.message.trim() && 
          c.subject === conv.subject &&
          c.direction === conv.direction
        );
      });

      uniqueConversations.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
      setConversations(uniqueConversations);
    } else {
      console.log('No conversation data or not an array');
      setConversations([]);
    }
  }, [contact]);

  useEffect(() => {
    if (conversations.length > 0 && !didInitialScroll.current) {
      // Instant snap to bottom ONLY on the first load
      conversationEndRef.current?.scrollIntoView({ behavior: 'auto' });
      didInitialScroll.current = true;
    }
  }, [conversations]);

  // Robust Sort
  const sortedConversations = [...conversations].sort((a, b) => {
    const tA = new Date(a.timestamp).getTime();
    const tB = new Date(b.timestamp).getTime();
    return tA - tB;
  });

  const formatTime = (date) => {
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatDate = (date) => {
    if (!date || isNaN(date.getTime())) {
      return 'Today';
    }
    const today = new Date();
    const diffTime = today.getTime() - date.getTime();
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return date.toLocaleDateString('en-US', { weekday: 'long' });
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const handleSendDraft = async (draft) => {
    try {
      await sendEmail(contact.id, draft);
      setShowAutoDraft(false);
      // Refresh conversation
      window.location.reload();
    } catch (error) {
      console.error('Failed to send draft:', error);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-4xl h-[85vh] flex flex-col shadow-2xl">
        {/* Professional Header */}
        <div className="px-6 py-5 rounded-t-xl" style={{ background: 'linear-gradient(135deg, #6B64F2 0%, #8E5BF6 50%, #A656F7 100%)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-md">
                <span className="text-2xl">🏢</span>
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">{contact?.company}</h3>
                <p className="text-blue-100 text-sm">{contact?.name} • {contact?.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="text-white hover:bg-white/20 rounded-full p-2 transition-colors"
                aria-label="Close"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Conversation Area */}
        <div className="flex-1 overflow-y-auto bg-gray-50 p-6">
          {conversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <div className="w-20 h-20 bg-gray-200 rounded-full flex items-center justify-center mb-4">
                <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <p className="text-lg font-medium">No conversation history</p>
              <p className="text-sm mt-1">Conversations will appear here after emails are exchanged</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Statistics info */}
              {conversations.length > 0 && (
                <div className="bg-blue-50 p-3 rounded text-sm text-blue-800 flex items-center justify-between">
                  <span>
                    {conversations.length} {conversations.length === 1 ? 'message' : 'messages'}
                    {' '}({conversations.filter(c => c.direction === 'sent').length} sent, {conversations.filter(c => c.direction === 'received').length} received)
                  </span>
                </div>
              )}

              {sortedConversations.map((conv, idx) => {
                const showDate = idx === 0 ||
                  formatDate(conv.timestamp) !== formatDate(sortedConversations[idx - 1].timestamp);

                const isSent = conv.direction === 'sent';

                return (
                  <div key={conv.id || idx} className="space-y-2">
                    {showDate && (
                      <div className="flex items-center justify-center my-6">
                        <div className="bg-gray-200 text-gray-600 text-xs font-medium px-4 py-1.5 rounded-full">
                          {formatDate(conv.timestamp)}
                        </div>
                      </div>
                    )}

                    <div className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
                      <div className={`flex gap-3 max-w-[75%] ${isSent ? 'flex-row-reverse' : 'flex-row'}`}>
                        {/* Avatar */}
                        <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${isSent
                          ? 'bg-purple-600 text-white'
                          : 'bg-gray-300 text-gray-700'
                          }`}>
                          {isSent ? 'P' : 'H'}
                        </div>

                        {/* Message Bubble */}
                        <div className={`rounded-2xl px-4 py-3 shadow-sm ${isSent
                          ? 'bg-purple-100 text-purple-900 border border-purple-200 rounded-br-md'
                          : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md'
                          }`}>
                          {/* Subject */}
                          {conv.subject && (
                            <div className={`text-sm font-medium mb-2 ${isSent ? 'text-purple-700' : 'text-gray-600'
                              }`}>
                              {conv.subject}
                            </div>
                          )}

                          {/* Message Content */}
                          <div className="whitespace-pre-wrap text-sm leading-relaxed">
                            {conv.message || conv.content || 'No content available'}
                          </div>

                          {/* Timestamp */}
                          <div className={`text-xs mt-2 ${isSent ? 'text-purple-600' : 'text-gray-500'
                            }`}>
                            {formatTime(conv.timestamp)}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={conversationEndRef} />
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

export default EmailConversationModal;