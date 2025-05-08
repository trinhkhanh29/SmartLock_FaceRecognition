const uploadDicomImage = async (imageFile) => {
  const formData = new FormData();
  formData.append('file', imageFile);

  try {
    const response = await axios.post('/api/dicom/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    console.log('Image uploaded successfully:', response.data);
  } catch (error) {
    console.error('Error uploading DICOM image:', error);
  }
};
