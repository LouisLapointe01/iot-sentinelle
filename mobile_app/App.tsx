import React, { useState } from 'react';
import { StyleSheet, Text, View, Button, Alert, ActivityIndicator } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [text, setText] = useState('Not yet scanned');

  const handleBarCodeScanned = ({ data }: { type: string; data: string }) => {
    setScanned(true);
    setText(data);
    Alert.alert("Scanné", `Données : ${data}`);
  };

  // Permission is null while loading
  if (!permission) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#0000ff" />
      </View>
    );
  }

  // Permission is not granted
  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.maintext}>L'application a besoin de la caméra pour scanner les QR Codes.</Text>
        <Button onPress={requestPermission} title="Accorder la permission" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.cameraContainer}>
        <CameraView
          style={styles.camera}
          onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
          barcodeScannerSettings={{
            barcodeTypes: ["qr"],
          }}
        />
      </View>
      
      <View style={styles.infoContainer}>
        <Text style={styles.maintext}>{text}</Text>
        {scanned && (
          <Button title={'Scanner à nouveau'} onPress={() => setScanned(false)} color='tomato' />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  cameraContainer: {
    width: '100%',
    aspectRatio: 1,
    overflow: 'hidden',
    borderRadius: 20,
    marginBottom: 40,
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  maintext: {
    fontSize: 16,
    margin: 20,
    textAlign: 'center',
  },
  errorText: {
    color: 'red',
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 10,
  },
  infoContainer: {
    alignItems: 'center',
  }
});
