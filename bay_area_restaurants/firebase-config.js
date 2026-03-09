// =====================================================
// Firebase Configuration
// =====================================================
// SETUP INSTRUCTIONS (one-time, ~2 minutes):
//
// 1. Go to https://console.firebase.google.com
// 2. Click "Create a project" (or "Add project")
// 3. Name it anything (e.g. "bay-area-restaurants")
// 4. Once created, click the Web icon (</>) to add a Web app
// 5. Register the app (any nickname), then copy the firebaseConfig object below
// 6. Go to Firestore Database in the sidebar → "Create database"
//    - Choose "Start in test mode" → pick a region → Create
// 7. Replace the placeholder values below with your actual config
// =====================================================

const firebaseConfig = {
  apiKey: "AIzaSyBWIXVw0blwaMXQ6jWw4m-KAjT6RruifAM",
  authDomain: "restraunt-tracker.firebaseapp.com",
  projectId: "restraunt-tracker",
  storageBucket: "restraunt-tracker.firebasestorage.app",
  messagingSenderId: "45467756958",
  appId: "1:45467756958:web:b39251743efa43e13c0e8f",
  measurementId: "G-31MK9PK75D"
};

// Check if Firebase is configured
function isFirebaseConfigured() {
  return firebaseConfig.apiKey !== "YOUR_API_KEY" && typeof firebase !== 'undefined';
}

// Initialize Firebase (only if configured)
let db = null;

function initFirebase() {
  if (!isFirebaseConfigured()) {
    console.log('Firebase not configured. Using localStorage only. See firebase-config.js for setup instructions.');
    return false;
  }

  try {
    firebase.initializeApp(firebaseConfig);
    db = firebase.firestore();
    console.log('Firebase initialized successfully.');
    return true;
  } catch (error) {
    console.error('Firebase initialization error:', error);
    return false;
  }
}

// Firestore document path: app/data
const FIRESTORE_DOC = { collection: 'app', doc: 'data' };

// Write current localStorage state to Firestore
async function syncToFirestore() {
  if (!db) return;

  const indicator = document.getElementById('sync-indicator');
  if (indicator) indicator.className = 'sync-indicator syncing';

  try {
    const visits = JSON.parse(localStorage.getItem('restaurantVisits') || '{}');
    const customRestaurants = JSON.parse(localStorage.getItem('customRestaurants') || '[]');

    await db.collection(FIRESTORE_DOC.collection).doc(FIRESTORE_DOC.doc).set({
      visits: visits,
      customRestaurants: customRestaurants,
      lastUpdated: firebase.firestore.FieldValue.serverTimestamp()
    });

    if (indicator) indicator.className = 'sync-indicator synced';
    console.log('Synced to Firestore.');
  } catch (error) {
    console.error('Firestore sync error:', error);
    if (indicator) indicator.className = 'sync-indicator error';
  }
}

// Load data from Firestore and merge into localStorage
async function loadFromFirestore() {
  if (!db) return;

  const indicator = document.getElementById('sync-indicator');
  if (indicator) indicator.className = 'sync-indicator syncing';

  try {
    const docSnap = await db.collection(FIRESTORE_DOC.collection).doc(FIRESTORE_DOC.doc).get();

    if (!docSnap.exists) {
      console.log('No Firestore data found. Will create on first sync.');
      if (indicator) indicator.className = 'sync-indicator synced';
      return;
    }

    const data = docSnap.data();

    // Merge custom restaurants
    if (data.customRestaurants && data.customRestaurants.length > 0) {
      const local = JSON.parse(localStorage.getItem('customRestaurants') || '[]');
      const localIds = new Set(local.map(r => r.id));
      const merged = [...local];
      data.customRestaurants.forEach(r => {
        if (!localIds.has(r.id)) {
          merged.push(r);
        }
      });
      localStorage.setItem('customRestaurants', JSON.stringify(merged));
    }

    // Merge visits
    if (data.visits) {
      const localVisits = JSON.parse(localStorage.getItem('restaurantVisits') || '{}');
      Object.keys(data.visits).forEach(id => {
        if (!localVisits[id]) {
          localVisits[id] = data.visits[id];
        } else {
          const existingSet = new Set(localVisits[id].map(v => `${v.date}-${v.time}`));
          data.visits[id].forEach(v => {
            if (!existingSet.has(`${v.date}-${v.time}`)) {
              localVisits[id].push(v);
            }
          });
        }
      });
      localStorage.setItem('restaurantVisits', JSON.stringify(localVisits));
    }

    if (indicator) indicator.className = 'sync-indicator synced';
    console.log('Loaded data from Firestore.');
  } catch (error) {
    console.error('Firestore load error:', error);
    if (indicator) indicator.className = 'sync-indicator error';
  }
}
